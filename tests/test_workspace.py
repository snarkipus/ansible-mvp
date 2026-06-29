from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

from provenance.cli import main
from provenance.scheduler import write_mock_lsf_metadata
from provenance.workspace import materialize_inputs, prepare_workspace


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
                },
                "materialization": {
                    "inputs": {
                        "source_root": "fixtures/controlled_inputs",
                        "destination_root": "sim-run-root/input",
                        "logical_groups": ["dirA", "dirB", "dirC"],
                        "files": ["ex1.dat", "ex2.dat", "ex3.dat"],
                        "mode": "copy_from_controlled_source",
                    },
                    "runtime_scripts": ["run_script"],
                },
                "controlled_scripts": {
                    "run_script": {
                        "relative_path": "procs/run-script.sh",
                        "materialized_path": "sim-run-root/procs/run-script.sh",
                        "materialization_mode": "copy_from_controlled_source",
                    },
                },
                "scheduler": {
                    "mode": "mock_lsf",
                    "metadata_path": "provenance/scheduler/submission.yaml",
                    "require_real_lsf": False,
                },
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


def test_materialize_inputs_copies_repeated_groups_and_records_hashes(tmp_path: Path) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="demo_003", workspace_root=tmp_path)

    result = materialize_inputs(
        config_path=config_path,
        run_id="demo_003",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
        controlled_source_ref="controlled-source-demo-v0.1.0",
    )

    assert len(result.artifacts) == 9
    for group in ("dirA", "dirB", "dirC"):
        for name in ("ex1.dat", "ex2.dat", "ex3.dat"):
            assert (tmp_path / f"runs/demo_003/sim-run-root/input/{group}/{name}").is_file()
    dir_c_ex3 = next(
        artifact
        for artifact in result.artifacts
        if artifact.destination_path.as_posix().endswith("dirC/ex3.dat")
    )
    assert dir_c_ex3.source_resolved_commit == _git(controlled_repo, "rev-parse", "HEAD")
    assert dir_c_ex3.materialization_mode == "copy_from_controlled_source"
    assert dir_c_ex3.sha256 is not None and len(dir_c_ex3.sha256) == 64
    assert dir_c_ex3.sim_area == "input"
    assert dir_c_ex3.logical_group == "dirC"


def test_cli_materialize_procs_copies_runtime_script_and_writes_evidence(tmp_path: Path) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    output_path = (
        tmp_path / "runs/demo_004/provenance/inventories/materialized_runtime_scripts.json"
    )
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="demo_004", workspace_root=tmp_path)

    assert (
        main(
            [
                "materialize-procs",
                "--config",
                str(config_path),
                "--run-id",
                "demo_004",
                "--workspace-root",
                str(tmp_path),
                "--controlled-source-repo",
                str(controlled_repo),
                "--controlled-source-ref",
                "controlled-source-demo-v0.1.0",
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    script = tmp_path / "runs/demo_004/sim-run-root/procs/run-script.sh"
    assert script.is_file()
    assert script.stat().st_mode & 0o111
    evidence = json.loads(output_path.read_text(encoding="utf-8"))
    artifact = evidence["artifacts"][0]
    assert artifact["source_path"] == "procs/run-script.sh"
    assert artifact["destination_path"] == "runs/demo_004/sim-run-root/procs/run-script.sh"
    assert artifact["source_resolved_commit"] == _git(controlled_repo, "rev-parse", "HEAD")
    assert artifact["hash_status"] == "hashed"
    assert len(artifact["sha256"]) == 64
    assert artifact["role"] == "runtime_script"


def test_write_mock_lsf_metadata_records_absent_lsf_tools_without_failing(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="demo_005", workspace_root=tmp_path)

    payload = write_mock_lsf_metadata(
        config_path=config_path,
        run_id="demo_005",
        workspace_root=tmp_path,
        tool_resolver=lambda _name: None,
    )

    output_path = tmp_path / "runs/demo_005/provenance/scheduler/submission.yaml"
    assert output_path.is_file()
    written = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "mock_lsf"
    assert written["scheduler"] == "mock_lsf"
    assert written["real_lsf_required"] is False
    assert all(not tool["available"] for tool in written["real_lsf_tools"].values())
    assert written["metadata_path"] == "runs/demo_005/provenance/scheduler/submission.yaml"
    assert "sim-run-root" not in written["metadata_path"]


def test_cli_submit_mock_lsf_writes_scheduler_yaml(tmp_path: Path) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    output_path = tmp_path / "runs/demo_006/provenance/scheduler/submission.yaml"
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="demo_006", workspace_root=tmp_path)

    assert (
        main(
            [
                "submit-mock-lsf",
                "--config",
                str(config_path),
                "--run-id",
                "demo_006",
                "--workspace-root",
                str(tmp_path),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    metadata = yaml.safe_load(output_path.read_text(encoding="utf-8"))
    assert metadata["submission"]["job_id"] == "mock-demo_006"
    assert metadata["submission"]["command"] == "make submit-mock-lsf"
    assert metadata["provenance_root"] == "runs/demo_006/provenance"


def _create_controlled_source_repo(path: Path) -> Path:
    (path / "fixtures/controlled_inputs").mkdir(parents=True)
    for group in ("dirA", "dirB", "dirC"):
        group_path = path / "fixtures/controlled_inputs" / group
        group_path.mkdir()
        for name in ("ex1.dat", "ex2.dat", "ex3.dat"):
            (group_path / name).write_text(f"{group},{name}\n", encoding="utf-8")
    (path / "procs").mkdir()
    run_script = path / "procs/run-script.sh"
    run_script.write_text("#!/usr/bin/env bash\nset -euo pipefail\n", encoding="utf-8")
    run_script.chmod(0o755)
    _git(path, "init")
    _git(path, "add", "fixtures", "procs")
    _git(
        path,
        "-c",
        "user.name=Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "init",
    )
    _git(path, "tag", "controlled-source-demo-v0.1.0")
    return path


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", repo.as_posix(), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout.strip()
