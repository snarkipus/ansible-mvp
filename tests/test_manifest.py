import subprocess
from pathlib import Path
from typing import Any, cast

import yaml
from pytest import MonkeyPatch

from provenance.git_state import selected_tree_artifact_identity
from provenance.hashing import HashPolicy
from provenance.inventory import InventoryRecord
from provenance.manifest import (
    REQUIRED_TOP_LEVEL_SECTIONS,
    ManifestAssemblyInput,
    _validate_controlled_source_links,
    assemble_manifest,
    missing_required_key_values,
    missing_required_sections,
    semantic_consistency_errors,
    write_manifest,
)
from provenance.validation import CSVValidationEvidence, ValidationCheck, ValidationStatus


def test_assemble_manifest_connects_core_provenance_sections() -> None:
    input_record = InventoryRecord(
        relative_path="input/dirC/ex1.dat",
        size_bytes=10,
        mtime_ns=1,
        mtime_utc="2026-06-29T00:00:00Z",
        area_type="simulation",
        sim_area="input",
        product_area=None,
        logical_group="dirC",
        role="input",
        sha256="abc123",
    )
    raw_record = InventoryRecord(
        relative_path="lists/dirC/sim-out.dat",
        size_bytes=20,
        mtime_ns=2,
        mtime_utc="2026-06-29T00:00:01Z",
        area_type="simulation",
        sim_area="lists",
        product_area=None,
        logical_group="dirC",
        role="raw_output",
        sha256="def456",
    )
    validation = CSVValidationEvidence(
        path="products/extracted/required.csv",
        status=ValidationStatus.PASS,
        checks=(
            ValidationCheck(
                name="minimum_data_row_count",
                status=ValidationStatus.PASS,
                expected=">= 1",
                actual=2,
            ),
        ),
        size_bytes=30,
        total_rows=3,
        data_rows=2,
        header=("case", "value"),
        column_counts=(2, 2, 2),
    )

    manifest = cast(
        dict[str, Any],
        assemble_manifest(
            ManifestAssemblyInput(
                run={
                    "run_id": "demo_001",
                    "run_root": "runs/demo_001",
                    "started_at": "2026-06-29T00:00:00+00:00",
                    "finished_at": "2026-06-29T00:00:02+00:00",
                    "execution_context": {
                        "executed_by": "tester",
                        "hostname": "localhost",
                        "platform": "Linux",
                        "python_version": "3.12.0",
                        "git_version": "git version 2.0.0",
                    },
                },
                repositories=(
                    {
                        "name": "controlled-source-demo",
                        "path": Path("../controlled-source-demo"),
                        "requested_ref": "controlled-source-demo-v0.1.2",
                        "resolved_commit": "0" * 40,
                        "describe": "controlled-source-demo-v0.1.2",
                        "worktree_status": "clean",
                        "tracked_script_paths": ["procs/run-script.sh"],
                    },
                ),
                simulation_layout={
                    "sim_run_root": "runs/demo_001/sim-run-root",
                    "provenance_root": "runs/demo_001/provenance",
                },
                controlled_source_gate={
                    "status": "pass",
                    "checked_scripts": ["procs/run-script.sh"],
                },
                scheduler={"mode": "mock_lsf", "metadata_path": "scheduler/submission.yaml"},
                workflow={
                    "operator_flow": [
                        {
                            "stage": "simulation",
                            "display_name": "Run simulation",
                            "lifecycle_class": "factory",
                            "display_order": 60,
                            "status": "pass",
                        }
                    ]
                },
                inputs=(
                    {
                        **input_record.to_dict(),
                        "source_path": "fixtures/input/dirC/ex1.dat",
                        "run_path": "sim-run-root/input/dirC/ex1.dat",
                        "materialization_mode": "copy_from_controlled_source",
                    },
                ),
                runtime_scripts=(
                    {
                        "source_path": "procs/run-script.sh",
                        "run_path": "sim-run-root/procs/run-script.sh",
                        "materialization_mode": "copy_from_controlled_source",
                        "sha256": "789abc",
                    },
                ),
                stages=(
                    {
                        "name": "simulation",
                        "display_name": "Run simulation",
                        "lifecycle_class": "factory",
                        "display_order": 60,
                        "operator_visible": True,
                        "command": "procs/run-script.sh",
                        "working_directory": "runs/demo_001/sim-run-root",
                        "status": "pass",
                        "return_code": 0,
                        "logs": ["logs/simulation.stdout.log"],
                        "controlled_scripts": ["procs/run-script.sh"],
                        "inputs": ["input/dirC/ex1.dat"],
                        "outputs": ["lists/dirC/sim-out.dat"],
                    },
                ),
                raw_simulation_outputs=(raw_record,),
                derived_products=(
                    {
                        "relative_path": "products/extracted/required.csv",
                        "product_area": "extracted",
                        "role": "extracted_product",
                        "producing_stage": "extract_required",
                        "sha256": "fedcba",
                    },
                ),
                validations=(validation,),
                logs=({"stage": "simulation", "path": "logs/simulation.stdout.log"},),
                hash_policy=HashPolicy(),
                notes=("Synthetic MVP manifest assembled from helper records.",),
                config={"run_config": "configs/run.synthetic.yaml"},
            )
        ),
    )

    assert missing_required_sections(manifest) == ()
    assert tuple(manifest)[: len(REQUIRED_TOP_LEVEL_SECTIONS)] == REQUIRED_TOP_LEVEL_SECTIONS
    assert manifest["inputs"][0]["logical_group"] == "dirC"
    assert manifest["inputs"][0]["materialization_mode"] == "copy_from_controlled_source"
    assert manifest["runtime_scripts"][0]["run_path"] == "sim-run-root/procs/run-script.sh"
    assert manifest["stages"][0]["outputs"] == ["lists/dirC/sim-out.dat"]
    assert manifest["raw_simulation_outputs"][0]["sim_area"] == "lists"
    assert manifest["derived_products"][0]["product_area"] == "extracted"
    assert manifest["validations"][0]["status"] == "pass"
    assert manifest["hash_policy"]["algorithm"] == "sha256"
    assert manifest["config"]["run_config"] == "configs/run.synthetic.yaml"


def test_manifest_smoke_reports_missing_required_key_values() -> None:
    manifest = assemble_manifest(
        ManifestAssemblyInput(
            run={"run_id": ""},
            repositories=(),
            simulation_layout={"sim_run_root": "runs/demo_001/sim-run-root"},
            controlled_source_gate={"status": "pass"},
            scheduler={"mode": "mock_lsf"},
        )
    )

    missing = missing_required_key_values(manifest)

    assert "run.run_id" in missing
    assert "run.run_root" in missing
    assert "repositories" in missing
    assert "inputs" in missing
    assert "hash_policy.algorithm" not in missing


def test_manifest_smoke_reports_missing_required_top_level_sections() -> None:
    incomplete_manifest = {
        "manifest_version": "0.1",
        "run": {"run_id": "demo_001"},
        "repositories": [{"name": "controlled-source-demo"}],
    }

    missing = missing_required_sections(incomplete_manifest)

    assert "controlled_source_gate" in missing
    assert "raw_simulation_outputs" in missing
    assert "derived_products" in missing
    assert "notes" in missing
    assert "manifest_version" not in missing
    assert "run" not in missing
    assert "repositories" not in missing


def test_write_manifest_creates_yaml_file(tmp_path: Path) -> None:
    manifest = assemble_manifest(
        ManifestAssemblyInput(
            run={"run_id": "demo_001"},
            repositories=(),
            simulation_layout={"sim_run_root": "runs/demo_001/sim-run-root"},
            controlled_source_gate={"status": "pass"},
            scheduler={"mode": "mock_lsf"},
        )
    )

    destination = write_manifest(manifest, tmp_path / "provenance" / "manifest.yaml")

    assert destination.exists()
    loaded = yaml.safe_load(destination.read_text(encoding="utf-8"))
    assert loaded["manifest_version"] == "0.1"
    assert loaded["run"]["run_id"] == "demo_001"


def test_semantic_validation_uses_admitted_git_object_after_head_and_worktree_move(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "controlled"
    repo.mkdir()
    artifact = repo / "script.sh"
    artifact.write_text("admitted\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=repo, check=True, stdout=subprocess.DEVNULL)
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test User",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "admit",
        ],
        cwd=repo,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    admitted = selected_tree_artifact_identity(repo, "HEAD", "script.sh")
    subprocess.run(["git", "tag", "selected"], cwd=repo, check=True)
    artifact.write_text("new HEAD\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test User",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "move",
        ],
        cwd=repo,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(["git", "tag", "--force", "selected"], cwd=repo, check=True)
    artifact.write_text("dirty worktree\n", encoding="utf-8")
    config = tmp_path / "config.yaml"
    config.write_text("schema_version: '0.1'\nstages: []\nvalidations: {}\n", encoding="utf-8")
    manifest = {
        "run": {},
        "repositories": [
            {
                "path": repo.as_posix(),
                "resolved_commit": admitted.selected_commit,
                "selected_artifacts": [admitted.to_dict()],
            }
        ],
        "stages": [],
        "inputs": [],
        "runtime_scripts": [],
        "raw_simulation_outputs": [],
        "derived_products": [],
        "validations": [],
    }

    errors = semantic_consistency_errors(manifest, config_path=config, workspace_root=tmp_path)

    assert not [error for error in errors if error.startswith("repositories[")]


def test_manifest_semantics_revalidates_current_scheduler_components(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("schema_version: '0.1'\nstages: []\nvalidations: {}\n", encoding="utf-8")
    manifest = {
        "run": {"run_id": "demo_001"},
        "scheduler": {
            "job_id": "mock-demo_001",
            "receipt_validation": {
                "status": "pass",
                "errors": [],
                "run_id": "demo_001",
                "job_id": "mock-demo_001",
                "receipt_id": "receipt-1",
            },
        },
        "repositories": [],
        "stages": [],
        "inputs": [],
        "runtime_scripts": [],
        "raw_simulation_outputs": [],
        "derived_products": [],
        "validations": [],
    }
    calls: list[dict[str, object]] = []

    def current_receipt(**kwargs: object) -> dict[str, object]:
        calls.append(kwargs)
        return {
            "status": "fail",
            "errors": ["raw output hash does not match payload evidence"],
            "run_id": "demo_001",
            "job_id": "mock-demo_001",
            "receipt_id": "receipt-1",
        }

    monkeypatch.setattr("provenance.scheduler.validate_scheduler_receipt", current_receipt)

    errors = semantic_consistency_errors(manifest, config_path=config, workspace_root=tmp_path)

    assert calls == [
        {"config_path": config, "run_id": "demo_001", "workspace_root": tmp_path.resolve()}
    ]
    assert (
        "current scheduler evidence is inconsistent: "
        "raw output hash does not match payload evidence" in errors
    )


def test_manifest_semantics_accepts_current_scheduler_receipt_matching_manifest(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    config = tmp_path / "config.yaml"
    config.write_text("schema_version: '0.1'\nstages: []\nvalidations: {}\n", encoding="utf-8")
    manifest = {
        "run": {"run_id": "demo_001"},
        "scheduler": {
            "job_id": "mock-demo_001",
            "receipt_validation": {
                "status": "pass",
                "errors": [],
                "run_id": "demo_001",
                "job_id": "mock-demo_001",
                "receipt_id": "receipt-1",
            },
        },
        "repositories": [],
        "stages": [],
        "inputs": [],
        "runtime_scripts": [],
        "raw_simulation_outputs": [],
        "derived_products": [],
        "validations": [],
    }
    monkeypatch.setattr(
        "provenance.scheduler.validate_scheduler_receipt",
        lambda **_kwargs: {
            "status": "pass",
            "errors": [],
            "run_id": "demo_001",
            "job_id": "mock-demo_001",
            "receipt_id": "receipt-1",
        },
    )

    errors = semantic_consistency_errors(manifest, config_path=config, workspace_root=tmp_path)

    assert not [error for error in errors if error.startswith("current scheduler")]


def test_controlled_code_semantics_require_complete_exactly_once_selected_coverage() -> None:
    selected = [
        {
            "relative_path": "procs/run-script.sh",
            "role": "runtime_script",
            "source_category": "controlled_script",
        },
        {
            "relative_path": "scripts/extractor.py",
            "role": "controlled_code",
            "source_category": "controlled_script",
        },
    ]
    manifest: dict[str, object] = {
        "repositories": [{"resolved_commit": "a" * 40, "selected_artifacts": selected}],
        "runtime_scripts": [
            {"materialization": {"source_path": "procs/run-script.sh"}},
            {"materialization": {"source_path": "procs/run-script.sh"}},
        ],
        "inputs": [],
    }
    errors: list[str] = []

    _validate_controlled_source_links(manifest, errors)

    assert "runtime_scripts contains duplicate selected controlled-code identities" in errors
    assert any(
        "cover every selected controlled-code artifact exactly once" in error for error in errors
    )
