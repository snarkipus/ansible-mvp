"""Git repository and tracked script helpers for provenance preflight.

The functions in this module do not implement the full workflow preflight. They
provide small, typed building blocks that callers can use to fail early for
missing repositories, unresolved refs, dirty worktrees, and untracked scripts.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitStateError(RuntimeError):
    """Raised when Git cannot answer a required provenance question."""


@dataclass(frozen=True)
class WorktreeStatusEntry:
    """One porcelain-v1 Git status entry."""

    index_status: str
    worktree_status: str
    path: str

    @property
    def is_untracked(self) -> bool:
        """Return true when the entry represents an untracked path."""

        return self.index_status == "?" and self.worktree_status == "?"


@dataclass(frozen=True)
class RepositoryState:
    """Identity and cleanliness facts about a required repository."""

    path: Path
    exists: bool
    is_git_worktree: bool
    top_level: Path | None
    head_commit: str | None
    branch: str | None
    describe: str | None
    status_entries: tuple[WorktreeStatusEntry, ...]

    @property
    def is_clean(self) -> bool:
        """Return true when Git reports no tracked or untracked changes."""

        return self.is_git_worktree and not self.status_entries


@dataclass(frozen=True)
class RefResolution:
    """Result of resolving a Git ref, tag, branch, or commit-ish."""

    ref: str
    resolved_commit: str


@dataclass(frozen=True)
class TrackedFileState:
    """Git tracking and cleanliness facts for a repository-relative file."""

    repo_path: Path
    relative_path: str
    absolute_path: Path
    exists: bool
    is_file: bool
    is_tracked: bool
    is_dirty: bool
    blob_oid: str | None
    file_mode: str | None

    @property
    def is_clean_tracked_file(self) -> bool:
        """Return true when the path exists, is tracked, and has no local edits."""

        return self.exists and self.is_file and self.is_tracked and not self.is_dirty


@dataclass(frozen=True)
class ScriptIdentity:
    """Controlled script identity suitable for preflight and manifests."""

    repository: Path
    repository_commit: str | None
    relative_path: str
    absolute_path: Path
    exists: bool
    is_tracked: bool
    is_dirty: bool
    blob_oid: str | None
    file_mode: str | None
    executable: bool

    @property
    def is_usable(self) -> bool:
        """Return true when the script can be treated as controlled source."""

        return self.exists and self.is_tracked and not self.is_dirty


def capture_repository_state(repo_path: Path | str) -> RepositoryState:
    """Capture existence, Git identity, and dirty status for ``repo_path``."""

    path = Path(repo_path).expanduser().resolve()
    if not path.exists():
        return RepositoryState(
            path=path,
            exists=False,
            is_git_worktree=False,
            top_level=None,
            head_commit=None,
            branch=None,
            describe=None,
            status_entries=(),
        )

    top_level_result = _git(path, "rev-parse", "--show-toplevel", check=False)
    if top_level_result.returncode != 0:
        return RepositoryState(
            path=path,
            exists=True,
            is_git_worktree=False,
            top_level=None,
            head_commit=None,
            branch=None,
            describe=None,
            status_entries=(),
        )

    top_level = Path(top_level_result.stdout.strip()).resolve()
    head_commit = _git_stdout(top_level, "rev-parse", "HEAD")
    branch = _git_stdout(top_level, "branch", "--show-current") or None
    describe = _git_stdout(top_level, "describe", "--tags", "--always", "--dirty") or None
    status_output = _git(top_level, "status", "--porcelain=v1", "--untracked-files=all").stdout

    return RepositoryState(
        path=path,
        exists=True,
        is_git_worktree=True,
        top_level=top_level,
        head_commit=head_commit,
        branch=branch,
        describe=describe,
        status_entries=tuple(_parse_status_entries(status_output)),
    )


def resolve_ref(repo_path: Path | str, ref: str) -> RefResolution:
    """Resolve ``ref`` to a commit SHA in ``repo_path`` or raise ``GitStateError``."""

    repo = _require_git_worktree(repo_path)
    resolved = _git_stdout(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    if not resolved:
        raise GitStateError(f"ref does not resolve to a commit: {ref}")
    return RefResolution(ref=ref, resolved_commit=resolved)


def tracked_file_state(repo_path: Path | str, relative_path: str | Path) -> TrackedFileState:
    """Return Git tracking facts for a repository-relative file path."""

    repo = _require_git_worktree(repo_path)
    rel = _normalize_relative_path(relative_path)
    absolute = repo / rel
    exists = absolute.exists()
    is_file = absolute.is_file()
    ls_result = _git(repo, "ls-files", "--stage", "--", rel, check=False)
    mode: str | None = None
    blob_oid: str | None = None
    if ls_result.stdout.strip():
        first_line = ls_result.stdout.splitlines()[0]
        parts = first_line.split(maxsplit=3)
        if len(parts) >= 2:
            mode = parts[0]
            blob_oid = parts[1]

    is_tracked = blob_oid is not None
    status_result = _git(repo, "status", "--porcelain=v1", "--", rel, check=False)
    is_dirty = bool(status_result.stdout.strip())
    return TrackedFileState(
        repo_path=repo,
        relative_path=rel,
        absolute_path=absolute,
        exists=exists,
        is_file=is_file,
        is_tracked=is_tracked,
        is_dirty=is_dirty,
        blob_oid=blob_oid,
        file_mode=mode,
    )


def script_identity(repo_path: Path | str, relative_path: str | Path) -> ScriptIdentity:
    """Return controlled script identity details for a tracked script path."""

    repo_state = capture_repository_state(repo_path)
    if not repo_state.is_git_worktree or repo_state.top_level is None:
        raise GitStateError(f"not a Git worktree: {Path(repo_path)}")

    file_state = tracked_file_state(repo_state.top_level, relative_path)
    return ScriptIdentity(
        repository=repo_state.top_level,
        repository_commit=repo_state.head_commit,
        relative_path=file_state.relative_path,
        absolute_path=file_state.absolute_path,
        exists=file_state.exists,
        is_tracked=file_state.is_tracked,
        is_dirty=file_state.is_dirty,
        blob_oid=file_state.blob_oid,
        file_mode=file_state.file_mode,
        executable=file_state.absolute_path.exists()
        and file_state.absolute_path.stat().st_mode & 0o111 != 0,
    )


def assert_clean_tracked_files(repo_path: Path | str, relative_paths: list[str | Path]) -> None:
    """Raise ``GitStateError`` if any configured path is missing, untracked, or dirty."""

    failures: list[str] = []
    for relative_path in relative_paths:
        state = tracked_file_state(repo_path, relative_path)
        if not state.exists:
            failures.append(f"missing: {state.relative_path}")
        elif not state.is_file:
            failures.append(f"not a file: {state.relative_path}")
        elif not state.is_tracked:
            failures.append(f"untracked: {state.relative_path}")
        elif state.is_dirty:
            failures.append(f"dirty: {state.relative_path}")

    if failures:
        raise GitStateError("configured Git-controlled paths failed checks: " + "; ".join(failures))


def _require_git_worktree(repo_path: Path | str) -> Path:
    state = capture_repository_state(repo_path)
    if not state.exists:
        raise GitStateError(f"repository path does not exist: {state.path}")
    if not state.is_git_worktree or state.top_level is None:
        raise GitStateError(f"not a Git worktree: {state.path}")
    return state.top_level


def _normalize_relative_path(path: str | Path) -> str:
    rel = Path(path)
    if rel.is_absolute() or ".." in rel.parts:
        raise GitStateError(f"path must be repository-relative and stay inside the repo: {path}")
    return rel.as_posix()


def _parse_status_entries(status_output: str) -> list[WorktreeStatusEntry]:
    entries: list[WorktreeStatusEntry] = []
    for line in status_output.splitlines():
        if not line:
            continue
        entries.append(
            WorktreeStatusEntry(
                index_status=line[0],
                worktree_status=line[1],
                path=line[3:],
            )
        )
    return entries


def _git_stdout(repo_path: Path, *args: str) -> str:
    return _git(repo_path, *args).stdout.strip()


def _git(repo_path: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and result.returncode != 0:
        command = " ".join(["git", "-C", str(repo_path), *args])
        raise GitStateError(f"Git command failed ({command}): {result.stderr.strip()}")
    return result
