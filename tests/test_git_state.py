from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from provenance.git_state import (
    GitStateError,
    assert_clean_tracked_files,
    capture_repository_state,
    resolve_ref,
    script_identity,
    tracked_file_state,
)


def test_capture_repository_state_reports_missing_repo(tmp_path: Path) -> None:
    state = capture_repository_state(tmp_path / "missing")

    assert state.exists is False
    assert state.is_git_worktree is False
    assert state.is_clean is False


def test_resolve_ref_and_script_identity_for_clean_tracked_script(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    script = repo / "scripts" / "run.sh"
    script.parent.mkdir()
    script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    _git(repo, "add", "scripts/run.sh")
    _git(repo, "commit", "-m", "add script")
    _git(repo, "tag", "v1")

    state = capture_repository_state(repo)
    resolved = resolve_ref(repo, "v1")
    identity = script_identity(repo, "scripts/run.sh")

    assert state.is_git_worktree is True
    assert state.is_clean is True
    assert resolved.resolved_commit == state.head_commit
    assert identity.repository_commit == state.head_commit
    assert identity.relative_path == "scripts/run.sh"
    assert identity.is_usable is True
    assert identity.executable is True
    assert identity.blob_oid
    assert identity.file_mode == "100755"


def test_script_identity_marks_untracked_scripts_unusable(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _git(repo, "commit", "--allow-empty", "-m", "initial")
    script = repo / "scripts" / "local-only.sh"
    script.parent.mkdir()
    script.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)

    identity = script_identity(repo, "scripts/local-only.sh")

    assert identity.exists is True
    assert identity.is_tracked is False
    assert identity.is_dirty is True
    assert identity.executable is True
    assert identity.is_usable is False
    assert identity.blob_oid is None
    assert identity.file_mode is None


def test_tracked_file_state_detects_untracked_and_dirty_paths(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    tracked = repo / "tracked.sh"
    tracked.write_text("original\n", encoding="utf-8")
    _git(repo, "add", "tracked.sh")
    _git(repo, "commit", "-m", "add tracked file")
    tracked.write_text("changed\n", encoding="utf-8")
    untracked = repo / "untracked.sh"
    untracked.write_text("new\n", encoding="utf-8")

    dirty_state = tracked_file_state(repo, "tracked.sh")
    untracked_state = tracked_file_state(repo, "untracked.sh")
    repo_state = capture_repository_state(repo)

    assert dirty_state.is_tracked is True
    assert dirty_state.is_dirty is True
    assert untracked_state.exists is True
    assert untracked_state.is_tracked is False
    assert untracked_state.is_dirty is True
    assert repo_state.is_clean is False
    assert {entry.path for entry in repo_state.status_entries} == {"tracked.sh", "untracked.sh"}


def test_assert_clean_tracked_files_reports_missing_untracked_and_dirty(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    dirty = repo / "dirty.sh"
    dirty.write_text("clean\n", encoding="utf-8")
    _git(repo, "add", "dirty.sh")
    _git(repo, "commit", "-m", "add dirty candidate")
    dirty.write_text("dirty\n", encoding="utf-8")
    (repo / "untracked.sh").write_text("untracked\n", encoding="utf-8")

    with pytest.raises(GitStateError) as error:
        assert_clean_tracked_files(repo, ["dirty.sh", "untracked.sh", "missing.sh"])

    message = str(error.value)
    assert "dirty: dirty.sh" in message
    assert "untracked: untracked.sh" in message
    assert "missing: missing.sh" in message


def test_repository_relative_paths_must_stay_inside_repo(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)

    with pytest.raises(GitStateError):
        tracked_file_state(repo, "../escape.sh")


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    return repo


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True)
