from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTROLLED_REF = "controlled-source-demo-v0.1.1"


def test_clean_synthetic_workflow_smoke_generates_manifest_reports_and_validation(
    tmp_path: Path,
) -> None:
    wrapper = _prepare_wrapper_checkout(tmp_path)
    _bootstrap_controlled_source(wrapper)
    run_id = "smoke_clean"

    _run(
        [
            "ansible-playbook",
            "ansible/playbooks/run_synthetic_workflow.yml",
            "-i",
            "ansible/inventory/localhost.ini",
            "-e",
            f"run_id={run_id}",
            "-e",
            "controlled_source_repo=../controlled-source-demo",
            "-e",
            f"controlled_source_ref={CONTROLLED_REF}",
        ],
        cwd=wrapper,
        env=_env_without_lsf_tools(),
    )

    run_root = wrapper / "runs" / run_id
    sim_root = run_root / "sim-run-root"
    provenance_root = run_root / "provenance"
    manifest_path = provenance_root / "manifest.yaml"
    required_validation = provenance_root / "validations" / "required_extract.json"

    assert (sim_root / "lists" / "dirC" / "sim-out.dat").is_file()
    assert (provenance_root / "products" / "extracted" / "required.csv").is_file()
    assert (provenance_root / "products" / "reports" / "summary.xlsx").is_file()
    assert (provenance_root / "products" / "reports" / "chart.png").is_file()
    assert (provenance_root / "products" / "reports" / "briefing.pptx").is_file()
    assert not (sim_root / "products").exists()
    assert not (sim_root / "provenance").exists()

    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    assert manifest["run"]["started_at"]
    assert manifest["run"]["finished_at"]
    execution_context = manifest["run"]["execution_context"]
    assert execution_context["executed_by"]
    assert execution_context["hostname"]
    assert execution_context["platform"]
    assert execution_context["python_version"]
    assert execution_context["git_version"].startswith("git version")
    assert manifest["controlled_source_gate"]["status"] == "pass"
    assert manifest["scheduler"]["mode"] == "mock_lsf"
    assert manifest["raw_simulation_outputs"][0]["relative_path"] == "lists/dirC/sim-out.dat"
    assert manifest["raw_simulation_outputs"][0]["sim_area"] == "lists"
    assert manifest["raw_simulation_outputs"][0]["logical_group"] == "dirC"
    report_names = {Path(record["relative_path"]).name for record in manifest["derived_products"]}
    assert {"summary.xlsx", "chart.png", "briefing.pptx"}.issubset(report_names)
    assert any(record["status"] == "pass" for record in manifest["validations"])
    assert yaml.safe_load(required_validation.read_text(encoding="utf-8"))["status"] == "pass"
    configured_stages = _load_run_config(wrapper)["stages"]
    configured_stage_names = [stage["name"] for stage in configured_stages]
    manifest_stage_names = [stage["name"] for stage in manifest["stages"]]
    assert manifest_stage_names == configured_stage_names
    for configured_stage, manifest_stage in zip(configured_stages, manifest["stages"], strict=True):
        assert manifest_stage["display_name"] == configured_stage["display_name"]
        assert manifest_stage["lifecycle_class"] == configured_stage["lifecycle_class"]
        assert manifest_stage["display_order"] == configured_stage["display_order"]
        assert manifest_stage["operator_visible"] == configured_stage["operator_visible"]
    assert [entry["stage"] for entry in manifest["workflow"]["operator_flow"]] == [
        stage["name"] for stage in configured_stages if stage["operator_visible"]
    ]
    support_stage_names = {
        "preflight",
        "prepare_workspace",
        "materialize_inputs",
        "materialize_procs",
        "submit_mock_lsf",
        "inventory_pre",
        "inventory_post",
        "validate",
        "manifest",
        "manifest_smoke",
    }
    for stage_name in support_stage_names:
        evidence_path = provenance_root / "logs" / f"{stage_name}.stage.json"
        assert evidence_path.is_file()
        evidence = yaml.safe_load(evidence_path.read_text(encoding="utf-8"))
        assert evidence["name"] == stage_name
        assert evidence["status"] == "pass"
        assert evidence["command"]
        assert evidence["cwd"] == evidence["working_directory"]
        assert evidence["evidence_path"] == f"runs/{run_id}/provenance/logs/{stage_name}.stage.json"
        assert evidence["started_at"]
        assert evidence["finished_at"]
        assert evidence["return_code"] == 0
        assert "inputs" in evidence
        assert "outputs" in evidence


def test_preflight_smoke_rejects_dirty_controlled_source(tmp_path: Path) -> None:
    wrapper = _prepare_wrapper_checkout(tmp_path)
    controlled = _bootstrap_controlled_source(wrapper)
    (controlled / "untracked-input.dat").write_text("not controlled\n", encoding="utf-8")

    result = _run_make_preflight(wrapper, check=False)

    assert result.returncode != 0
    assert "controlled source repository is dirty" in _combined_output(result)


def test_preflight_rejects_existing_run_id_unless_reuse_policy_is_explicit(
    tmp_path: Path,
) -> None:
    wrapper = _prepare_wrapper_checkout(tmp_path)
    _bootstrap_controlled_source(wrapper)
    run_id = "duplicate_run"
    (wrapper / "runs" / run_id).mkdir()

    rejected = _run_make_preflight(wrapper, run_id=run_id, check=False)
    reused = _run_make_preflight(wrapper, run_id=run_id, run_root_policy="reuse")

    assert rejected.returncode != 0
    assert "run root already exists" in _combined_output(rejected)
    assert reused.returncode == 0


def test_preflight_smoke_rejects_dirty_wrapper_controlled_path(tmp_path: Path) -> None:
    wrapper = _prepare_wrapper_checkout(tmp_path)
    _bootstrap_controlled_source(wrapper)
    with (wrapper / "Makefile").open("a", encoding="utf-8") as makefile:
        makefile.write("\n# smoke-test dirty controlled path\n")

    result = _run_make_preflight(wrapper, check=False)

    assert result.returncode != 0
    assert "dirty: Makefile" in _combined_output(result)


def test_preflight_smoke_rejects_untracked_script(tmp_path: Path) -> None:
    wrapper = _prepare_wrapper_checkout(tmp_path)
    controlled = _bootstrap_controlled_source(wrapper)
    untracked = controlled / "scripts" / "untracked.sh"
    untracked.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
    untracked.chmod(0o755)
    config = _load_run_config(wrapper)
    config["controlled_scripts"]["untracked_smoke"] = {
        "repository": "controlled_source",
        "relative_path": "scripts/untracked.sh",
        "executable": True,
    }
    config["stages"][0]["expected_controlled_scripts"].append("untracked_smoke")
    _write_config_and_commit(wrapper, config, "reference untracked script")

    result = _run_make_preflight(wrapper, check=False)

    assert result.returncode != 0
    assert "controlled script untracked_smoke is untracked" in _combined_output(result)


def test_preflight_smoke_rejects_uncontrolled_stage_command_and_missing_ref(
    tmp_path: Path,
) -> None:
    wrapper = _prepare_wrapper_checkout(tmp_path)
    _bootstrap_controlled_source(wrapper)
    config = _load_run_config(wrapper)
    config["stages"][0]["approved_command_path"] = "scripts/evil.sh"
    _write_config_and_commit(wrapper, config, "reference uncontrolled stage command")

    uncontrolled = _run_make_preflight(wrapper, check=False)
    missing_ref = _run_make_preflight(wrapper, ref="missing-ref", check=False)

    assert uncontrolled.returncode != 0
    assert "uncontrolled approved_command_path" in _combined_output(uncontrolled)
    assert missing_ref.returncode != 0
    assert "controlled source ref failed to resolve" in _combined_output(missing_ref)


def _prepare_wrapper_checkout(tmp_path: Path) -> Path:
    wrapper = tmp_path / "ansible-mvp"
    shutil.copytree(
        ROOT,
        wrapper,
        ignore=shutil.ignore_patterns(
            ".git",
            ".beads",
            ".basedpyright_cache",
            ".pytest_cache",
            ".ruff_cache",
            ".venv",
            "__pycache__",
            "runs",
        ),
    )
    (wrapper / "runs").mkdir()
    (wrapper / "runs" / ".gitkeep").write_text("", encoding="utf-8")
    _run(["git", "init"], cwd=wrapper)
    _run(["git", "config", "user.email", "smoke@example.invalid"], cwd=wrapper)
    _run(["git", "config", "user.name", "Smoke Test"], cwd=wrapper)
    _run(["git", "add", "."], cwd=wrapper)
    _run(["git", "commit", "-m", "smoke wrapper baseline"], cwd=wrapper)
    return wrapper


def _bootstrap_controlled_source(wrapper: Path) -> Path:
    _run(["make", "bootstrap-controlled-source"], cwd=wrapper)
    return wrapper.parent / "controlled-source-demo"


def _run_make_preflight(
    wrapper: Path,
    *,
    run_id: str = "demo_001",
    ref: str = CONTROLLED_REF,
    run_root_policy: str = "fresh",
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return _run(
        [
            "make",
            "preflight",
            f"RUN_ID={run_id}",
            f"CONTROLLED_SOURCE_REF={ref}",
            f"RUN_ROOT_POLICY={run_root_policy}",
        ],
        cwd=wrapper,
        check=check,
    )


def _load_run_config(wrapper: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(
        (wrapper / "configs" / "run.synthetic.yaml").read_text(encoding="utf-8")
    )
    assert isinstance(loaded, dict)
    return loaded


def _write_config_and_commit(wrapper: Path, config: dict[str, Any], message: str) -> None:
    config_path = wrapper / "configs" / "run.synthetic.yaml"
    config_path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    _run(["git", "add", "configs/run.synthetic.yaml"], cwd=wrapper)
    _run(["git", "commit", "-m", message], cwd=wrapper)


def _env_without_lsf_tools() -> dict[str, str]:
    lsf_tools = ("bsub", "bjobs", "bhist", "bacct")
    installed_lsf_tools = [tool for tool in lsf_tools if shutil.which(tool) is not None]
    if installed_lsf_tools:
        pytest.skip(f"real LSF tools are installed: {', '.join(installed_lsf_tools)}")
    return os.environ.copy()


def _run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return f"{result.stdout}\n{result.stderr}"
