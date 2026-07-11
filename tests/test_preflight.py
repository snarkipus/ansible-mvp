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
        controlled_source_ref="controlled-source-demo-v0.1.2",
    )

    assert result.status == "pass"
    assert result.controlled_source_repo["resolved_commit"]
    assert result.controlled_scripts[0]["is_usable"] is True
    assert result.wrapper_factory_definition
    assert all(record["blob_oid"] for record in result.wrapper_factory_definition)
    assert all(len(record["sha256"]) == 64 for record in result.wrapper_factory_definition)
    assert {artifact["role"] for artifact in result.controlled_artifacts} == {
        "runtime_script",
        "input",
    }
    assert {artifact["source_category"] for artifact in result.controlled_artifacts} == {
        "controlled_script",
        "controlled_input",
    }
    assert all(artifact["selected_commit"] for artifact in result.controlled_artifacts)
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
            controlled_source_ref="controlled-source-demo-v0.1.2",
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


@pytest.mark.parametrize(
    ("command", "expected_message"),
    [
        ("sh -c 'make preflight'", "command invokes shell interpreter"),
        ("bash -c 'make preflight'", "command invokes shell interpreter"),
        ("python script.py > output.csv", "command uses shell-style syntax"),
        ("make preflight | tee output.log", "command uses shell-style syntax"),
        ("make preflight && make prepare-workspace", "command uses shell-style syntax"),
        ("make $(printf preflight)", "command uses shell-style syntax"),
        ("make `printf preflight`", "command uses shell-style syntax"),
    ],
)
def test_preflight_rejects_shell_style_stage_commands(
    tmp_path: Path, command: str, expected_message: str
) -> None:
    wrapper, controlled, config = _prepare_repositories(tmp_path)
    config_payload = yaml.safe_load(config.read_text(encoding="utf-8"))
    config_payload["stages"][0]["command"] = command
    config.write_text(yaml.safe_dump(config_payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(PreflightError) as error:
        run_preflight(
            config_path=config,
            wrapper_repo=wrapper,
            controlled_source_repo=controlled,
            controlled_source_ref="controlled-source-demo-v0.1.2",
        )

    assert expected_message in str(error.value)


def test_preflight_rejects_uncontrolled_scheduler_payload_command(tmp_path: Path) -> None:
    wrapper, controlled, config = _prepare_repositories(tmp_path)
    config_payload = yaml.safe_load(config.read_text(encoding="utf-8"))
    config_payload["stages"][1]["command_kind"] = "wrapper_make_target"
    config_payload["stages"][1]["command"] = "make run-simulation"
    config_payload["stages"][1]["approved_command_path"] = "Makefile"
    config.write_text(yaml.safe_dump(config_payload, sort_keys=False), encoding="utf-8")

    with pytest.raises(PreflightError) as error:
        run_preflight(
            config_path=config,
            wrapper_repo=wrapper,
            controlled_source_repo=controlled,
            controlled_source_ref="controlled-source-demo-v0.1.2",
        )

    assert "scheduler payload" in str(error.value)


def test_preflight_rejects_ignored_input_absent_from_selected_commit(tmp_path: Path) -> None:
    wrapper, controlled, config = _prepare_repositories(tmp_path)
    (controlled / ".gitignore").write_text("fixtures/dirA/local-only.dat\n", encoding="utf-8")
    _git(controlled, "add", ".gitignore")
    _git(controlled, "commit", "-m", "ignore local input")
    (controlled / "fixtures" / "dirA").mkdir(exist_ok=True)
    (controlled / "fixtures" / "dirA" / "local-only.dat").write_text("local\n", encoding="utf-8")
    config_payload = yaml.safe_load(config.read_text(encoding="utf-8"))
    config_payload["materialization"]["inputs"]["source_root"] = "fixtures"
    config_payload["materialization"]["inputs"]["files"] = ["local-only.dat"]
    config.write_text(yaml.safe_dump(config_payload, sort_keys=False), encoding="utf-8")
    _git(wrapper, "add", "run.synthetic.yaml")
    _git(wrapper, "commit", "-m", "reference ignored input")

    with pytest.raises(PreflightError, match="absent from selected commit"):
        run_preflight(
            config_path=config,
            wrapper_repo=wrapper,
            controlled_source_repo=controlled,
            controlled_source_ref="controlled-source-demo-v0.1.2",
        )


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
    fixture = controlled / "fixtures" / "controlled_inputs" / "dirA" / "ex1.dat"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("controlled input\n", encoding="utf-8")

    _git(wrapper, "add", ".gitignore", "runs/.gitkeep", "Makefile")
    _git(wrapper, "commit", "-m", "wrapper")
    _git(controlled, "add", "procs/run-script.sh", "fixtures")
    _git(controlled, "commit", "-m", "controlled")
    _git(controlled, "tag", "controlled-source-demo-v0.1.2")

    config = wrapper / "run.synthetic.yaml"
    config.write_text(yaml.safe_dump(_config_payload(), sort_keys=False), encoding="utf-8")
    _git(wrapper, "add", "run.synthetic.yaml")
    _git(wrapper, "commit", "-m", "config")
    return wrapper, controlled, config


def _config_payload() -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "layout": {
            "run_root": "runs/{run_id}",
            "sim_run_root": "runs/{run_id}/sim-run-root",
            "provenance_root": "runs/{run_id}/provenance",
            "simulation_areas": ["input", "lists", "files", "procs"],
            "provenance_directories": [
                "logs",
                "inventories",
                "scheduler",
                "validations",
                "products/extracted",
                "products/reports",
            ],
            "canonical_raw_output": "lists/dirC/sim-out.dat",
        },
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
                "materialized_path": "sim-run-root/procs/run-script.sh",
                "materialization_mode": "copy_from_controlled_source",
                "executable": True,
            }
        },
        "approved_command_paths": {
            "wrapper": ["Makefile"],
            "controlled_source": ["procs/run-script.sh"],
        },
        "approved_make_targets": [
            "preflight",
            "submit-mock-lsf",
            "wait-mock-lsf",
            "collect-mock-lsf",
        ],
        "materialization": {
            "inputs": {
                "source_root": "fixtures/controlled_inputs",
                "destination_root": "sim-run-root/input",
                "logical_groups": ["dirA"],
                "files": ["ex1.dat"],
                "mode": "copy_from_controlled_source",
            },
            "runtime_scripts": ["run_script"],
        },
        "scheduler": {
            "mode": "mock_lsf",
            "emulator_execution_mode": "local_async",
            "metadata_path": "provenance/scheduler/submission.yaml",
            "require_real_lsf": False,
            "payload_stage": "run_simulation",
            "payload_command": "procs/run-script.sh",
            "payload_command_kind": "materialized_controlled_script",
            "payload_approved_command_path": "procs/run-script.sh",
            "poll_interval_seconds": 0.1,
            "wait_timeout_seconds": 1,
            "runtime_delay": {
                "min_seconds": 0,
                "max_seconds": 0,
                "jitter": "deterministic_run_id",
            },
            "approved_make_targets": [
                "submit-mock-lsf",
                "wait-mock-lsf",
                "collect-mock-lsf",
            ],
        },
        "stage_defaults": {"log_directory": "provenance/logs"},
        "stages": [
            {
                "name": "preflight",
                "display_name": "Preflight",
                "lifecycle_class": "admission",
                "display_order": 10,
                "operator_visible": True,
                "command": "make preflight",
                "working_directory": "wrapper_repo",
                "command_kind": "wrapper_make_target",
                "approved_command_path": "Makefile",
                "expected_controlled_scripts": ["run_script"],
            },
            {
                "name": "run_simulation",
                "display_name": "Run simulation",
                "lifecycle_class": "factory",
                "display_order": 20,
                "operator_visible": False,
                "command": "procs/run-script.sh",
                "working_directory": "sim-run-root",
                "command_kind": "materialized_controlled_script",
                "approved_command_path": "procs/run-script.sh",
                "expected_controlled_scripts": ["run_script"],
            },
        ],
        "validations": {
            "required_extract": {
                "config_path": "expected.yaml",
                "product_path": "provenance/products/extracted/required.csv",
                "evidence_path": "provenance/validations/required_extract.json",
            }
        },
        "manifest": {"output_path": "provenance/manifest.yaml"},
    }


def _init_repo(path: Path) -> Path:
    path.mkdir()
    _git(path, "init")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    return path


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True)
