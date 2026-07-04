from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load_yaml(relative_path: str) -> dict[str, object]:
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
    assert group_vars["default_controlled_source_ref"] == "controlled-source-demo-v0.1.0"
    assert group_vars["workflow_stage_targets"] == [
        "preflight",
        "prepare-workspace",
        "materialize-inputs",
        "materialize-procs",
        "inventory-pre",
        "submit-mock-lsf",
        "run-simulation",
        "extract-required",
        "extract-ad-hoc",
        "build-reports",
        "validate",
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
    rendered_playbook = yaml.safe_dump(play)
    assert "run_id | default(default_run_id)" in rendered_playbook
    assert "controlled_source_repo | default(default_controlled_source_repo)" in rendered_playbook
    assert "controlled_source_ref | default(default_controlled_source_ref)" in rendered_playbook
    assert "RUN_ID=" in rendered_playbook
    assert "workflow_run_id" in rendered_playbook
    assert "CONTROLLED_SOURCE_REPO=" in rendered_playbook
    assert "workflow_controlled_source_repo" in rendered_playbook
    assert "CONTROLLED_SOURCE_REF=" in rendered_playbook
    assert "workflow_controlled_source_ref" in rendered_playbook


def test_ansible_paths_are_wrapper_controlled_paths() -> None:
    run_config = _load_yaml("configs/run.synthetic.yaml")

    controlled_paths = set(run_config["repositories"]["wrapper"]["controlled_paths"])
    assert {
        "ansible/inventory/localhost.ini",
        "ansible/inventory/group_vars/all.yml",
        "ansible/playbooks/run_synthetic_workflow.yml",
    }.issubset(controlled_paths)
