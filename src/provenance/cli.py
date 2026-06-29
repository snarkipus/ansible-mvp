"""Command-line entry points for provenance helper operations.

The CLI is intentionally thin: it exposes the typed helper modules for Make,
Ansible, and tests without embedding orchestration policy. Commands write
JSON/YAML evidence to stdout by default, or to an explicit output path when one
is supplied.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn, Sequence

import yaml

from provenance.git_state import (
    GitStateError,
    capture_repository_state,
    resolve_ref,
    script_identity,
    tracked_file_state,
)
from provenance.hashing import hash_artifact
from provenance.inventory import InventoryRecord, inventory_files, with_sha256
from provenance.manifest import (
    ManifestAssemblyInput,
    assemble_manifest,
    missing_required_sections,
    write_manifest,
)
from provenance.preflight import PreflightError, run_preflight
from provenance.reports import build_report_product_evidence
from provenance.scheduler import write_mock_lsf_metadata
from provenance.stages import (
    run_ad_hoc_extraction,
    run_required_extraction,
    run_synthetic_simulation,
)
from provenance.validation import CSVShapeExpectation, validate_csv_product
from provenance.workspace import materialize_inputs, materialize_runtime_scripts, prepare_workspace


def main(argv: Sequence[str] | None = None) -> int:
    """Run the provenance CLI and return a process exit code."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (
        GitStateError,
        PreflightError,
        FileNotFoundError,
        NotADirectoryError,
        ValueError,
    ) as exc:
        parser.exit(2, f"provenance: error: {exc}\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="provenance", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    git_state = subparsers.add_parser("git-state", help="capture Git repository facts")
    git_state.add_argument("repo", type=Path)
    git_state.add_argument("--ref", action="append", default=[], help="ref to resolve")
    git_state.add_argument(
        "--tracked-file", action="append", default=[], help="repo-relative tracked file to inspect"
    )
    git_state.add_argument(
        "--script", action="append", default=[], help="repo-relative controlled script to inspect"
    )
    git_state.add_argument("--output", type=Path, help="optional JSON output path")
    git_state.set_defaults(func=_cmd_git_state)

    preflight = subparsers.add_parser("preflight", help="run controlled-source preflight gate")
    preflight.add_argument("--config", type=Path, default=Path("configs/run.synthetic.yaml"))
    preflight.add_argument("--wrapper-repo", type=Path, default=Path("."))
    preflight.add_argument("--controlled-source-repo", type=Path, required=True)
    preflight.add_argument("--controlled-source-ref", required=True)
    preflight.add_argument("--output", type=Path, help="optional JSON output path")
    preflight.set_defaults(func=_cmd_preflight)

    workspace = subparsers.add_parser(
        "prepare-workspace", help="prepare separated run and provenance workspaces"
    )
    workspace.add_argument("--config", type=Path, default=Path("configs/run.synthetic.yaml"))
    workspace.add_argument("--run-id", required=True)
    workspace.add_argument("--workspace-root", type=Path, default=Path("."))
    workspace.add_argument("--output", type=Path, help="optional JSON output path")
    workspace.set_defaults(func=_cmd_prepare_workspace)

    materialize_inputs_parser = subparsers.add_parser(
        "materialize-inputs", help="copy controlled inputs into the run workspace"
    )
    _add_materialization_arguments(materialize_inputs_parser)
    materialize_inputs_parser.set_defaults(func=_cmd_materialize_inputs)

    materialize_procs = subparsers.add_parser(
        "materialize-procs", help="copy controlled runtime scripts into the run workspace"
    )
    _add_materialization_arguments(materialize_procs)
    materialize_procs.set_defaults(func=_cmd_materialize_procs)

    mock_lsf = subparsers.add_parser("submit-mock-lsf", help="write mock LSF scheduler metadata")
    mock_lsf.add_argument("--config", type=Path, default=Path("configs/run.synthetic.yaml"))
    mock_lsf.add_argument("--run-id", required=True)
    mock_lsf.add_argument("--workspace-root", type=Path, default=Path("."))
    mock_lsf.add_argument("--output", type=Path, help="optional scheduler YAML output path")
    mock_lsf.set_defaults(func=_cmd_submit_mock_lsf)

    run_simulation = subparsers.add_parser(
        "run-simulation", help="execute the controlled synthetic simulation stage"
    )
    run_simulation.add_argument("--config", type=Path, default=Path("configs/run.synthetic.yaml"))
    run_simulation.add_argument("--run-id", required=True)
    run_simulation.add_argument("--workspace-root", type=Path, default=Path("."))
    run_simulation.add_argument("--controlled-source-repo", type=Path, required=True)
    run_simulation.add_argument("--output", type=Path, help="optional stage JSON output path")
    run_simulation.set_defaults(func=_cmd_run_simulation)

    extract_required = subparsers.add_parser(
        "extract-required", help="execute the controlled required extraction stage"
    )
    extract_required.add_argument("--config", type=Path, default=Path("configs/run.synthetic.yaml"))
    extract_required.add_argument("--run-id", required=True)
    extract_required.add_argument("--workspace-root", type=Path, default=Path("."))
    extract_required.add_argument("--controlled-source-repo", type=Path, required=True)
    extract_required.add_argument("--output", type=Path, help="optional stage JSON output path")
    extract_required.set_defaults(func=_cmd_extract_required)

    extract_ad_hoc = subparsers.add_parser(
        "extract-ad-hoc", help="execute the controlled ad hoc extraction stage"
    )
    extract_ad_hoc.add_argument("--config", type=Path, default=Path("configs/run.synthetic.yaml"))
    extract_ad_hoc.add_argument("--run-id", required=True)
    extract_ad_hoc.add_argument("--workspace-root", type=Path, default=Path("."))
    extract_ad_hoc.add_argument("--controlled-source-repo", type=Path, required=True)
    extract_ad_hoc.add_argument("--output", type=Path, help="optional stage JSON output path")
    extract_ad_hoc.set_defaults(func=_cmd_extract_ad_hoc)

    build_reports = subparsers.add_parser(
        "build-reports", help="generate minimal XLSX, PNG, and PPTX report products"
    )
    build_reports.add_argument("--run-id", required=True)
    build_reports.add_argument("--workspace-root", type=Path, default=Path("."))
    build_reports.add_argument("--output", type=Path, help="optional report inventory JSON path")
    build_reports.add_argument("--stage-output", type=Path, help="optional stage JSON output path")
    build_reports.set_defaults(func=_cmd_build_reports)

    inventory = subparsers.add_parser("inventory", help="inventory files under a root")
    inventory.add_argument("root", type=Path)
    inventory.add_argument("--with-hashes", action="store_true", help="include SHA-256 hashes")
    inventory.add_argument("--output", type=Path, help="optional JSON output path")
    inventory.set_defaults(func=_cmd_inventory)

    inventory_pre = subparsers.add_parser(
        "inventory-pre", help="write pre-run input and controlled-script inventories"
    )
    inventory_pre.add_argument("--run-id", required=True)
    inventory_pre.add_argument("--workspace-root", type=Path, default=Path("."))
    inventory_pre.add_argument("--inputs-output", type=Path)
    inventory_pre.add_argument("--scripts-output", type=Path)
    inventory_pre.set_defaults(func=_cmd_inventory_pre)

    inventory_post = subparsers.add_parser(
        "inventory-post", help="write post-run raw-output and derived-product inventories"
    )
    inventory_post.add_argument("--run-id", required=True)
    inventory_post.add_argument("--workspace-root", type=Path, default=Path("."))
    inventory_post.add_argument("--raw-output", type=Path)
    inventory_post.add_argument("--products-output", type=Path)
    inventory_post.set_defaults(func=_cmd_inventory_post)

    validate_csv = subparsers.add_parser("validate-csv", help="validate CSV shape")
    validate_csv.add_argument("path", type=Path)
    validate_csv.add_argument("--display-path", help="path to record in validation evidence")
    validate_csv.add_argument("--expected-data-rows", type=int)
    validate_csv.add_argument("--minimum-data-rows", type=int)
    validate_csv.add_argument("--expected-column-count", type=int)
    validate_csv.add_argument("--expected-header", help="comma-separated expected CSV header")
    validate_csv.add_argument("--output", type=Path, help="optional JSON output path")
    validate_csv.set_defaults(func=_cmd_validate_csv)

    assemble = subparsers.add_parser("assemble-manifest", help="assemble manifest YAML")
    assemble.add_argument("input", type=Path, help="YAML mapping of manifest assembly fields")
    assemble.add_argument("--output", type=Path, required=True, help="manifest YAML output path")
    assemble.set_defaults(func=_cmd_assemble_manifest)

    smoke = subparsers.add_parser("smoke-manifest", help="smoke-validate manifest sections")
    smoke.add_argument("manifest", type=Path)
    smoke.add_argument("--output", type=Path, help="optional JSON output path")
    smoke.set_defaults(func=_cmd_smoke_manifest)

    return parser


def _cmd_git_state(args: argparse.Namespace) -> int:
    repo = capture_repository_state(args.repo)
    payload: dict[str, Any] = {
        "repository": {
            "path": repo.path.as_posix(),
            "exists": repo.exists,
            "is_git_worktree": repo.is_git_worktree,
            "top_level": repo.top_level.as_posix() if repo.top_level is not None else None,
            "head_commit": repo.head_commit,
            "branch": repo.branch,
            "describe": repo.describe,
            "is_clean": repo.is_clean,
            "status_entries": [entry.__dict__ for entry in repo.status_entries],
        },
        "refs": [],
        "tracked_files": [],
        "scripts": [],
    }
    for ref in args.ref:
        payload["refs"].append(resolve_ref(args.repo, ref).__dict__)
    for relative_path in args.tracked_file:
        payload["tracked_files"].append(_tracked_file_payload(args.repo, relative_path))
    for relative_path in args.script:
        payload["scripts"].append(_script_payload(args.repo, relative_path))

    _write_json(payload, args.output)
    return 0


def _cmd_preflight(args: argparse.Namespace) -> int:
    result = run_preflight(
        config_path=args.config,
        wrapper_repo=args.wrapper_repo,
        controlled_source_repo=args.controlled_source_repo,
        controlled_source_ref=args.controlled_source_ref,
    )
    _write_json(result.to_dict(), args.output)
    return 0


def _cmd_prepare_workspace(args: argparse.Namespace) -> int:
    result = prepare_workspace(
        config_path=args.config,
        run_id=args.run_id,
        workspace_root=args.workspace_root,
    )
    _write_json(result.to_dict(), args.output)
    return 0


def _cmd_materialize_inputs(args: argparse.Namespace) -> int:
    result = materialize_inputs(
        config_path=args.config,
        run_id=args.run_id,
        controlled_source_repo=args.controlled_source_repo,
        controlled_source_ref=args.controlled_source_ref,
        workspace_root=args.workspace_root,
    )
    _write_json(result.to_dict(), args.output)
    return 0


def _cmd_materialize_procs(args: argparse.Namespace) -> int:
    result = materialize_runtime_scripts(
        config_path=args.config,
        run_id=args.run_id,
        controlled_source_repo=args.controlled_source_repo,
        controlled_source_ref=args.controlled_source_ref,
        workspace_root=args.workspace_root,
    )
    _write_json(result.to_dict(), args.output)
    return 0


def _cmd_submit_mock_lsf(args: argparse.Namespace) -> int:
    payload = write_mock_lsf_metadata(
        config_path=args.config,
        run_id=args.run_id,
        workspace_root=args.workspace_root,
        output=args.output,
    )
    _write_json(payload, None)
    return 0


def _cmd_run_simulation(args: argparse.Namespace) -> int:
    result = run_synthetic_simulation(
        config_path=args.config,
        run_id=args.run_id,
        workspace_root=args.workspace_root,
        controlled_source_repo=args.controlled_source_repo,
    )
    _write_json(result.to_dict(), args.output)
    return 0 if result.status == "pass" else 1


def _cmd_extract_required(args: argparse.Namespace) -> int:
    result = run_required_extraction(
        config_path=args.config,
        run_id=args.run_id,
        workspace_root=args.workspace_root,
        controlled_source_repo=args.controlled_source_repo,
    )
    _write_json(result.to_dict(), args.output)
    return 0 if result.status == "pass" else 1


def _cmd_extract_ad_hoc(args: argparse.Namespace) -> int:
    result = run_ad_hoc_extraction(
        config_path=args.config,
        run_id=args.run_id,
        workspace_root=args.workspace_root,
        controlled_source_repo=args.controlled_source_repo,
    )
    _write_json(result.to_dict(), args.output)
    return 0 if result.status == "pass" else 1


def _cmd_build_reports(args: argparse.Namespace) -> int:
    started_at = time.time()
    records = build_report_product_evidence(run_id=args.run_id, workspace_root=args.workspace_root)
    finished_at = time.time()
    _write_json(list(records), args.output)
    if args.stage_output is not None:
        _write_report_stage_evidence(
            run_id=args.run_id,
            workspace_root=args.workspace_root,
            output=args.stage_output,
            products=records,
            started_at=started_at,
            finished_at=finished_at,
        )
    return 0


def _write_report_stage_evidence(
    *,
    run_id: str,
    workspace_root: Path,
    output: Path,
    products: Sequence[dict[str, str | int | None]],
    started_at: float,
    finished_at: float,
) -> None:
    root = workspace_root.expanduser().resolve()
    provenance_root = root / "runs" / run_id / "provenance"
    log_root = provenance_root / "logs"
    log_root.mkdir(parents=True, exist_ok=True)
    stdout_log = log_root / "build_reports.stdout.log"
    stderr_log = log_root / "build_reports.stderr.log"
    stdout_log.write_text("Generated report products.\n", encoding="utf-8")
    stderr_log.write_text("", encoding="utf-8")
    run_root = root / "runs" / run_id
    payload = {
        "name": "build_reports",
        "command": "make build-reports",
        "working_directory": ".",
        "logs": {
            "stdout": stdout_log.relative_to(root).as_posix(),
            "stderr": stderr_log.relative_to(root).as_posix(),
        },
        "started_at": _format_epoch_timestamp(started_at),
        "finished_at": _format_epoch_timestamp(finished_at),
        "duration_seconds": round(finished_at - started_at, 6),
        "status": "pass",
        "return_code": 0,
        "controlled_scripts": [],
        "inputs": [
            _report_stage_artifact(run_root, Path("provenance/products/extracted/required.csv")),
            _report_stage_artifact(run_root, Path("provenance/products/extracted/ad_hoc.csv")),
        ],
        "outputs": list(products),
    }
    _write_json(payload, output)


def _report_stage_artifact(run_root: Path, relative_path: Path) -> dict[str, str | bool | None]:
    return {
        "relative_path": relative_path.as_posix(),
        "exists": (run_root / relative_path).exists(),
        "sim_area": None,
        "logical_group": None,
        "role": "extracted_product",
        "sha256": None,
        "hash_status": None,
    }


def _format_epoch_timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, UTC).isoformat().replace("+00:00", "Z")


def _cmd_inventory(args: argparse.Namespace) -> int:
    records = inventory_files(args.root)
    if args.with_hashes:
        records = tuple(
            with_sha256(record, hash_artifact(args.root / record.relative_path).sha256 or "")
            for record in records
        )
    _write_json([record.to_dict() for record in records], args.output)
    return 0


def _cmd_inventory_pre(args: argparse.Namespace) -> int:
    root = args.workspace_root.expanduser().resolve()
    run_root = root / "runs" / args.run_id
    sim_root = run_root / "sim-run-root"
    inventory_root = run_root / "provenance" / "inventories"
    inputs_output = args.inputs_output or inventory_root / "pre_run_inputs.json"
    scripts_output = args.scripts_output or inventory_root / "pre_run_controlled_scripts.json"

    inputs = _pre_run_inventory_records(
        root=root,
        sim_root=sim_root,
        area="input",
        materialization_evidence=inventory_root / "materialized_inputs.json",
    )
    scripts = _pre_run_inventory_records(
        root=root,
        sim_root=sim_root,
        area="procs",
        materialization_evidence=inventory_root / "materialized_runtime_scripts.json",
    )
    _write_json(inputs, inputs_output)
    _write_json(scripts, scripts_output)
    _write_json(
        {
            "status": "pass",
            "inputs_inventory": inputs_output.as_posix(),
            "controlled_scripts_inventory": scripts_output.as_posix(),
            "input_count": len(inputs),
            "controlled_script_count": len(scripts),
        },
        None,
    )
    return 0


def _cmd_inventory_post(args: argparse.Namespace) -> int:
    root = args.workspace_root.expanduser().resolve()
    run_root = root / "runs" / args.run_id
    sim_root = run_root / "sim-run-root"
    provenance_root = run_root / "provenance"
    inventory_root = provenance_root / "inventories"
    raw_output = args.raw_output or inventory_root / "post_run_raw_outputs.json"
    products_output = args.products_output or inventory_root / "post_run_derived_products.json"

    raw_outputs = _post_run_raw_output_records(root=root, run_root=run_root, sim_root=sim_root)
    products = _post_run_derived_product_records(
        root=root, run_root=run_root, provenance_root=provenance_root
    )
    _write_json(raw_outputs, raw_output)
    _write_json(products, products_output)
    _write_json(
        {
            "status": "pass",
            "raw_outputs_inventory": raw_output.as_posix(),
            "derived_products_inventory": products_output.as_posix(),
            "raw_output_count": len(raw_outputs),
            "derived_product_count": len(products),
        },
        None,
    )
    return 0


def _pre_run_inventory_records(
    *, root: Path, sim_root: Path, area: str, materialization_evidence: Path
) -> list[dict[str, Any]]:
    records = tuple(
        record
        for record in inventory_files(sim_root)
        if record.relative_path == area or record.relative_path.startswith(f"{area}/")
    )
    materialized_by_destination = _materialized_artifacts_by_destination(materialization_evidence)
    payload: list[dict[str, Any]] = []
    for record in records:
        hashed = with_sha256(record, hash_artifact(sim_root / record.relative_path).sha256 or "")
        run_relative_path = (sim_root / hashed.relative_path).relative_to(root).as_posix()
        entry: dict[str, Any] = dict(hashed.to_dict())
        entry["run_relative_path"] = run_relative_path
        entry["hash_status"] = "hashed"
        entry["materialization"] = materialized_by_destination.get(run_relative_path)
        payload.append(entry)
    return payload


def _post_run_raw_output_records(
    *, root: Path, run_root: Path, sim_root: Path
) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for record in inventory_files(sim_root):
        if record.role != "raw_output":
            continue
        hashed = with_sha256(record, hash_artifact(sim_root / record.relative_path).sha256 or "")
        absolute_path = sim_root / hashed.relative_path
        entry: dict[str, Any] = dict(hashed.to_dict())
        entry["workflow_relative_path"] = absolute_path.relative_to(run_root).as_posix()
        entry["run_relative_path"] = absolute_path.relative_to(root).as_posix()
        entry["hash_status"] = "hashed"
        payload.append(entry)
    return payload


def _post_run_derived_product_records(
    *, root: Path, run_root: Path, provenance_root: Path
) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for record in inventory_files(provenance_root):
        if record.area_type != "product":
            continue
        hashed = with_sha256(
            record, hash_artifact(provenance_root / record.relative_path).sha256 or ""
        )
        absolute_path = provenance_root / hashed.relative_path
        entry: dict[str, Any] = dict(hashed.to_dict())
        entry["workflow_relative_path"] = absolute_path.relative_to(run_root).as_posix()
        entry["run_relative_path"] = absolute_path.relative_to(root).as_posix()
        entry["hash_status"] = "hashed"
        entry["producing_stage"] = _producing_stage_for_product(hashed)
        payload.append(entry)
    return payload


def _producing_stage_for_product(record: InventoryRecord) -> str | None:
    if record.product_area == "reports":
        return "build_reports"
    if record.product_area == "extracted":
        name = Path(record.relative_path).name
        if name == "required.csv":
            return "extract_required"
        if name == "ad_hoc.csv":
            return "extract_ad_hoc"
    return None


def _materialized_artifacts_by_destination(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"materialization evidence must be a mapping: {path}")
    artifacts = loaded.get("artifacts", [])
    if not isinstance(artifacts, list):
        raise ValueError(f"materialization evidence artifacts must be a list: {path}")
    by_destination: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            raise ValueError(f"materialization artifact must be a mapping: {path}")
        destination = artifact.get("destination_path")
        if isinstance(destination, str) and destination:
            by_destination[destination] = artifact
    return by_destination


def _add_materialization_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, default=Path("configs/run.synthetic.yaml"))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--workspace-root", type=Path, default=Path("."))
    parser.add_argument("--controlled-source-repo", type=Path, required=True)
    parser.add_argument("--controlled-source-ref", required=True)
    parser.add_argument("--output", type=Path, help="optional JSON output path")


def _cmd_validate_csv(args: argparse.Namespace) -> int:
    expectation = CSVShapeExpectation(
        expected_data_rows=args.expected_data_rows,
        minimum_data_rows=args.minimum_data_rows,
        expected_column_count=args.expected_column_count,
        expected_header=tuple(args.expected_header.split(",")) if args.expected_header else None,
    )
    evidence = validate_csv_product(args.path, expectation, display_path=args.display_path)
    _write_json(evidence.to_dict(), args.output)
    return 0 if evidence.passed else 1


def _cmd_assemble_manifest(args: argparse.Namespace) -> int:
    source = _read_yaml_mapping(args.input)
    manifest = assemble_manifest(ManifestAssemblyInput(**source))
    write_manifest(manifest, args.output)
    _write_json({"status": "pass", "manifest": args.output.as_posix()}, None)
    return 0


def _cmd_smoke_manifest(args: argparse.Namespace) -> int:
    manifest = _read_yaml_mapping(args.manifest)
    missing = missing_required_sections(manifest)
    payload = {
        "status": "pass" if not missing else "fail",
        "manifest": args.manifest.as_posix(),
        "missing_required_sections": list(missing),
    }
    _write_json(payload, args.output)
    return 0 if not missing else 1


def _tracked_file_payload(repo: Path, relative_path: str) -> dict[str, Any]:
    state = tracked_file_state(repo, relative_path)
    return {
        "repo_path": state.repo_path.as_posix(),
        "relative_path": state.relative_path,
        "absolute_path": state.absolute_path.as_posix(),
        "exists": state.exists,
        "is_file": state.is_file,
        "is_tracked": state.is_tracked,
        "is_dirty": state.is_dirty,
        "is_clean_tracked_file": state.is_clean_tracked_file,
        "blob_oid": state.blob_oid,
        "file_mode": state.file_mode,
    }


def _script_payload(repo: Path, relative_path: str) -> dict[str, Any]:
    state = script_identity(repo, relative_path)
    return {
        "repository": state.repository.as_posix(),
        "repository_commit": state.repository_commit,
        "relative_path": state.relative_path,
        "absolute_path": state.absolute_path.as_posix(),
        "exists": state.exists,
        "is_tracked": state.is_tracked,
        "is_dirty": state.is_dirty,
        "blob_oid": state.blob_oid,
        "file_mode": state.file_mode,
        "executable": state.executable,
        "is_usable": state.is_usable,
    }


def _read_yaml_mapping(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as file_obj:
        loaded = yaml.safe_load(file_obj) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"YAML input must be a mapping: {path}")
    return loaded


def _write_json(payload: object, output: Path | None) -> None:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    if output is None:
        print(text, end="")
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text, encoding="utf-8")


def _entrypoint() -> NoReturn:
    raise SystemExit(main())


if __name__ == "__main__":
    _entrypoint()
