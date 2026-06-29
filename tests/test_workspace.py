from __future__ import annotations

from pathlib import Path

import yaml

from provenance.cli import main
from provenance.workspace import prepare_workspace


def _write_config(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
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
                }
            }
        ),
        encoding="utf-8",
    )


def test_prepare_workspace_creates_separated_simulation_and_provenance_dirs(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    _write_config(config_path)

    result = prepare_workspace(
        config_path=config_path,
        run_id="demo_001",
        workspace_root=tmp_path,
    )

    sim_root = tmp_path / "runs/demo_001/sim-run-root"
    provenance_root = tmp_path / "runs/demo_001/provenance"
    for area in ("input", "lists", "files", "procs"):
        assert (sim_root / area).is_dir()
    for relative_path in (
        "logs",
        "inventories",
        "scheduler",
        "validations",
        "products/extracted",
        "products/reports",
    ):
        assert (provenance_root / relative_path).is_dir()

    assert not (sim_root / "provenance").exists()
    assert result.to_dict()["provenance_root"] == "runs/demo_001/provenance"


def test_cli_prepare_workspace_writes_json_evidence(tmp_path: Path) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    output_path = tmp_path / "workspace.json"
    _write_config(config_path)

    assert (
        main(
            [
                "prepare-workspace",
                "--config",
                str(config_path),
                "--run-id",
                "demo_002",
                "--workspace-root",
                str(tmp_path),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    assert (tmp_path / "runs/demo_002/sim-run-root/input").is_dir()
    assert (tmp_path / "runs/demo_002/provenance/products/reports").is_dir()
    assert "runs/demo_002/sim-run-root/provenance" not in output_path.read_text(encoding="utf-8")
