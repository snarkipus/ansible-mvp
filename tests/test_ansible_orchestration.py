from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from provenance.stages import configured_harness_make_targets

ROOT = Path(__file__).resolve().parents[1]


def _load_yaml(relative_path: str) -> dict[str, Any]:
    with (ROOT / relative_path).open(encoding="utf-8") as file_obj:
        loaded = yaml.safe_load(file_obj)
    assert isinstance(loaded, dict)
    return loaded


def test_local_inventory_declares_localhost_connection() -> None:
    inventory = (ROOT / "ansible/inventory/localhost.ini").read_text(encoding="utf-8")

    assert "[provenance_mvp]" in inventory
    assert "localhost" in inventory
    assert "ansible_connection=local" in inventory


def test_group_vars_define_documented_defaults_and_stage_order() -> None:
    group_vars = _load_yaml("ansible/inventory/group_vars/all.yml")
    run_config = _load_yaml("configs/run.synthetic.yaml")

    assert group_vars["default_run_id"] == run_config["run"]["default_run_id"]
    assert group_vars["default_controlled_source_repo"] == "../controlled-source-demo"
    assert group_vars["default_controlled_source_ref"] == "controlled-source-demo-v0.1.2"
    assert list(configured_harness_make_targets(ROOT / "configs/run.synthetic.yaml")) == [
        "preflight",
        "prepare-workspace",
        "materialize-inputs",
        "materialize-procs",
        "inventory-pre",
        "submit-mock-lsf",
        "wait-mock-lsf",
        "collect-mock-lsf",
        "extract-required",
        "extract-ad-hoc",
        "validate",
        "build-reports",
        "inventory-post",
        "manifest",
        "manifest-smoke",
    ]


def test_playbook_uses_documented_extra_vars_and_make_contract() -> None:
    playbook = yaml.safe_load(
        (ROOT / "ansible/playbooks/run_synthetic_workflow.yml").read_text(encoding="utf-8")
    )
    assert isinstance(playbook, list)
    play = playbook[0]

    assert play["hosts"] == "provenance_mvp"
    stage_tasks = yaml.safe_load(
        (ROOT / "ansible/tasks/run_workflow_stage.yml").read_text(encoding="utf-8")
    )
    assert isinstance(stage_tasks, list)
    rendered_contract = yaml.safe_dump([play, stage_tasks])
    assert "run_id | default(default_run_id)" in rendered_contract
    assert "^[A-Za-z0-9][A-Za-z0-9._-]*$" in rendered_contract
    assert "controlled_source_repo | default(default_controlled_source_repo)" in rendered_contract
    assert "controlled_source_ref | default(default_controlled_source_ref)" in rendered_contract
    assert "RUN_ID=" in rendered_contract
    assert "workflow_run_id" in rendered_contract
    assert "CONTROLLED_SOURCE_REPO=" in rendered_contract
    assert "workflow_controlled_source_repo" in rendered_contract
    assert "CONTROLLED_SOURCE_REF=" in rendered_contract
    assert "workflow_controlled_source_ref" in rendered_contract
    assert "list-run-stage-targets" in rendered_contract
    assert "from_json" in rendered_contract
    assert "loop" in rendered_contract


def test_stage_failure_output_is_concise_and_actionable() -> None:
    stage_tasks = yaml.safe_load(
        (ROOT / "ansible/tasks/run_workflow_stage.yml").read_text(encoding="utf-8")
    )
    execute, report = stage_tasks

    assert execute["failed_when"] is False
    assert execute["register"] == "workflow_stage_result"
    message = report["ansible.builtin.fail"]["msg"]
    assert "Workflow stage" in message
    assert "workflow_stage_result.rc" in message
    assert "Stage evidence" in message
    assert "scheduler_receipt.json" in message
    assert "Focused rerun" in message
    assert "reject('match', '^make:')" in message


def test_ansible_paths_are_wrapper_controlled_paths() -> None:
    run_config = _load_yaml("configs/run.synthetic.yaml")

    controlled_paths = set(run_config["repositories"]["wrapper"]["controlled_paths"])
    assert {
        "ansible/inventory/localhost.ini",
        "ansible/inventory/group_vars/all.yml",
        "ansible/playbooks/run_synthetic_workflow.yml",
        "ansible/tasks/run_workflow_stage.yml",
    }.issubset(controlled_paths)
