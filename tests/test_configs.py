from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def _load_yaml(relative_path: str) -> dict[str, object]:
    with (ROOT / relative_path).open(encoding="utf-8") as file_obj:
        loaded = yaml.safe_load(file_obj)
    assert isinstance(loaded, dict)
    return loaded


def test_run_config_declares_controlled_scripts_and_stage_commands() -> None:
    config = _load_yaml("configs/run.synthetic.yaml")

    controlled_scripts = config["controlled_scripts"]
    assert isinstance(controlled_scripts, dict)
    assert set(controlled_scripts) == {
        "run_script",
        "synthetic_sim_engine",
        "extract_required",
        "ad_hoc_extract",
    }
    assert controlled_scripts["run_script"]["materialized_path"] == (
        "sim-run-root/procs/run-script.sh"
    )

    stages = config["stages"]
    assert isinstance(stages, list)
    stage_names = [stage["name"] for stage in stages]
    assert stage_names == [
        "preflight",
        "prepare_workspace",
        "materialize_inputs",
        "materialize_procs",
        "submit_mock_lsf",
        "run_simulation",
        "extract_required",
        "extract_ad_hoc",
        "build_reports",
        "inventory_pre",
        "inventory_post",
        "validate",
        "manifest",
        "manifest_smoke",
    ]

    script_names = set(controlled_scripts)
    for stage in stages:
        assert stage["approved_command_path"]
        assert stage["working_directory"]
        assert set(stage.get("expected_controlled_scripts", ())).issubset(script_names)


def test_run_config_links_layout_hash_policy_and_validation_expectations() -> None:
    config = _load_yaml("configs/run.synthetic.yaml")
    shape = _load_yaml("configs/expected_shape.required_extract.yaml")

    assert config["layout"]["sim_run_root"] == "runs/{run_id}/sim-run-root"
    assert config["layout"]["provenance_root"] == "runs/{run_id}/provenance"
    assert "products/extracted" in config["layout"]["provenance_directories"]
    assert config["hash_policy"]["algorithm"] == "sha256"
    assert config["scheduler"]["mode"] == "mock_lsf"
    assert config["scheduler"]["require_real_lsf"] is False

    required_extract = config["validations"]["required_extract"]
    assert required_extract["config_path"] == "configs/expected_shape.required_extract.yaml"
    assert required_extract["product_path"] == shape["product"]["relative_path"]
    assert required_extract["evidence_path"] == shape["evidence"]["output_path"]
    assert shape["expectations"] == {
        "expected_header": ["logical_group", "example", "bytes", "sha256_prefix"],
        "expected_column_count": 4,
        "minimum_data_rows": 1,
        "non_empty": True,
    }


def test_run_config_stages_declare_lifecycle_metadata() -> None:
    config = _load_yaml("configs/run.synthetic.yaml")

    stages = config["stages"]
    assert isinstance(stages, list)
    display_orders: list[int] = []
    for stage in stages:
        assert isinstance(stage, dict)
        assert stage["lifecycle_class"] in {"admission", "setup", "factory", "finalization"}
        assert isinstance(stage["display_order"], int)
        assert isinstance(stage["operator_visible"], bool)
        display_orders.append(stage["display_order"])

    assert display_orders == sorted(display_orders)
