from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from provenance.config import read_config_mapping

ROOT = Path(__file__).resolve().parents[1]


def _load_yaml(relative_path: str) -> dict[str, Any]:
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
        "inventory_pre",
        "submit_mock_lsf",
        "run_simulation",
        "extract_required",
        "extract_ad_hoc",
        "build_reports",
        "validate",
        "inventory_post",
        "manifest",
        "manifest_smoke",
    ]

    script_names = set(controlled_scripts)
    for stage in stages:
        assert stage["approved_command_path"]
        assert stage["working_directory"]
        assert set(stage.get("expected_controlled_scripts", ())).issubset(script_names)


def test_run_config_controls_behavior_affecting_wrapper_files() -> None:
    config = _load_yaml("configs/run.synthetic.yaml")

    wrapper = config["repositories"]["wrapper"]
    assert isinstance(wrapper, dict)
    controlled_paths = set(wrapper["controlled_paths"])
    assert {
        "pyproject.toml",
        "uv.lock",
        "src/provenance/__init__.py",
        "src/provenance/config.py",
    }.issubset(controlled_paths)


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


def test_config_loader_accepts_supported_schema_version() -> None:
    config = read_config_mapping(ROOT / "configs/run.synthetic.yaml")

    assert config["schema_version"] == "0.1"


def test_config_loader_rejects_unsupported_schema_version(tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text('schema_version: "9.9"\n', encoding="utf-8")

    try:
        read_config_mapping(config_path)
    except ValueError as error:
        assert "schema_version must be '0.1'" in str(error)
    else:  # pragma: no cover - assertion guard
        raise AssertionError("unsupported schema_version should fail")


def test_run_config_stages_declare_lifecycle_metadata() -> None:
    config = _load_yaml("configs/run.synthetic.yaml")

    stages = config["stages"]
    assert isinstance(stages, list)
    display_orders: list[int] = []
    for stage in stages:
        assert isinstance(stage, dict)
        assert isinstance(stage["display_name"], str)
        assert stage["display_name"]
        assert stage["lifecycle_class"] in {
            "admission",
            "setup",
            "evidence",
            "factory",
            "finalization",
        }
        assert isinstance(stage["display_order"], int)
        assert isinstance(stage["operator_visible"], bool)
        display_orders.append(stage["display_order"])

    assert display_orders == sorted(display_orders)
