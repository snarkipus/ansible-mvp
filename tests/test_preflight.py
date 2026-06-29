from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from provenance.preflight import PreflightError, run_preflight


def test_preflight_passes_for_clean_controlled_repositories(tmp_path: Path) -> None:
    wrapper, controlled, config = _prepare_repositories(tmp_path)
    (wrapper / "runs" / "demo_001" / "provenance").mkdir(parents=True)
    (wrapper / "runs" / "demo_001" / "provenance" / "ignored.json").write_text(
        "{}\n", encoding="utf-8"
    )

    result = run_preflight(
        config_path=config,
        wrapper_repo=wrapper,
        controlled_source_repo=controlled,
        controlled_source_ref="controlled-source-demo-v0.1.0",
    )

    assert result.status == "pass"
    assert result.controlled_source_repo["resolved_commit"]
    assert result.controlled_scripts[0]["is_usable"] is True
    assert result.stages[0]["approved_command_path"] == "Makefile"


def test_preflight_fails_for_dirty_wrapper_controlled_path_but_not_untracked_runs(
    tmp_path: Path,
) -> None:
    wrapper, controlled, config = _prepare_repositories(tmp_path)
    (wrapper / "runs" / "demo_001" / "provenance").mkdir(parents=True)
    (wrapper / "runs" / "demo_001" / "provenance" / "ignored.json").write_text(
        "{}\n", encoding="utf-8"
    )
    (wrapper / "Makefile").write_text("preflight:\n\t@exit 1\n", encoding="utf-8")

    with pytest.raises(PreflightError) as error:
        run_preflight(
            config_path=config,
            wrapper_repo=wrapper,
            controlled_source_repo=controlled,
            controlled_source_ref="controlled-source-demo-v0.1.0",
        )

    message = str(error.value)
    assert "dirty: Makefile" in message
    assert "ignored.json" not in message


def test_preflight_fails_for_missing_ref_untracked_script_and_uncontrolled_stage(
    tmp_path: Path,
) -> None:
    wrapper, controlled, config = _prepare_repositories(tmp_path)
    untracked = controlled / "scripts" / "untracked.sh"
    untracked.parent.mkdir()
    untracked.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    untracked.chmod(0o755)
    config_payload = yaml.safe_load(config.read_text(encoding="utf-8"))
    config_payload["controlled_scripts"]["untracked"] = {
        "repository": "controlled_source",
        "relative_path": "scripts/untracked.sh",
        "executable": True,
    }
    config_payload["stages"][0]["expected_controlled_scripts"] = ["untracked", "missing_name"]
    config_payload["stages"][0]["approved_command_path"] = "scripts/evil.sh"
    config.write_text(yaml.safe_dump(config_payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(PreflightError) as error:
        run_preflight(
            config_path=config,
            wrapper_repo=wrapper,
            controlled_source_repo=controlled,
            controlled_source_ref="missing-ref",
        )

    message = str(error.value)
    assert "controlled source ref failed to resolve" in message
    assert "controlled script untracked is untracked" in message
    assert "uncontrolled approved_command_path" in message
    assert "references unknown controlled script: missing_name" in message


def _prepare_repositories(tmp_path: Path) -> tuple[Path, Path, Path]:
    wrapper = _init_repo(tmp_path / "wrapper")
    controlled = _init_repo(tmp_path / "controlled-source-demo")

    (wrapper / ".gitignore").write_text("runs/*\n!runs/.gitkeep\n", encoding="utf-8")
    (wrapper / "runs").mkdir()
    (wrapper / "runs" / ".gitkeep").write_text("", encoding="utf-8")
    (wrapper / "Makefile").write_text("preflight:\n\t@exit 0\n", encoding="utf-8")

    (controlled / "procs").mkdir()
    (controlled / "procs" / "run-script.sh").write_text(
        "#!/usr/bin/env bash\nexit 0\n", encoding="utf-8"
    )
    (controlled / "procs" / "run-script.sh").chmod(0o755)

    _git(wrapper, "add", ".gitignore", "runs/.gitkeep", "Makefile")
    _git(wrapper, "commit", "-m", "wrapper")
    _git(controlled, "add", "procs/run-script.sh")
    _git(controlled, "commit", "-m", "controlled")
    _git(controlled, "tag", "controlled-source-demo-v0.1.0")

    config = wrapper / "run.synthetic.yaml"
    config.write_text(yaml.safe_dump(_config_payload(), sort_keys=False), encoding="utf-8")
    _git(wrapper, "add", "run.synthetic.yaml")
    _git(wrapper, "commit", "-m", "config")
    return wrapper, controlled, config


def _config_payload() -> dict[str, Any]:
    return {
        "repositories": {
            "wrapper": {
                "controlled_paths": ["Makefile", "run.synthetic.yaml"],
                "clean_policy": "configured_paths_only",
            },
            "controlled_source": {"require_clean_worktree": True},
        },
        "controlled_scripts": {
            "run_script": {
                "repository": "controlled_source",
                "relative_path": "procs/run-script.sh",
                "executable": True,
            }
        },
        "approved_command_paths": {
            "wrapper": ["Makefile"],
            "controlled_source": ["procs/run-script.sh"],
        },
        "stages": [
            {
                "name": "preflight",
                "command": "make preflight",
                "command_kind": "wrapper_make_target",
                "approved_command_path": "Makefile",
                "expected_controlled_scripts": ["run_script"],
            },
            {
                "name": "run_simulation",
                "command": "sim-run-root/procs/run-script.sh",
                "command_kind": "materialized_controlled_script",
                "approved_command_path": "procs/run-script.sh",
                "expected_controlled_scripts": ["run_script"],
            },
        ],
    }


def _init_repo(path: Path) -> Path:
    path.mkdir()
    _git(path, "init")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    return path


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True)
