"""Command-line entry points for provenance helper operations.

The CLI is intentionally thin: it exposes the typed helper modules for Make,
Ansible, and tests without embedding orchestration policy. Commands write
JSON/YAML evidence to stdout by default, or to an explicit output path when one
is supplied.
"""

from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator, NoReturn, Sequence

from provenance.config import read_config_mapping, read_yaml_mapping
from provenance.git_state import (
    GitStateError,
    capture_repository_state,
    resolve_ref,
    script_identity,
    tracked_file_state,
)
from provenance.hashing import hash_artifact, sha256_file
from provenance.inventory import inventory_files, with_sha256
from provenance.manifest import (
    ManifestAssemblyInput,
    assemble_manifest,
    assemble_run_manifest,
    missing_required_key_values,
    missing_required_sections,
    semantic_consistency_errors,
    write_manifest,
)
from provenance.paths import validate_run_id
from provenance.preflight import PreflightError, run_preflight
from provenance.reports import build_report_product_evidence
from provenance.scheduler import (
    collect_mock_lsf_accounting,
    submit_mock_lsf_job,
    wait_mock_lsf_job,
)
from provenance.stages import (
    configured_harness_make_targets,
    run_ad_hoc_extraction,
    run_required_extraction,
    run_synthetic_simulation,
    stage_attempt_evidence,
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
    preflight.add_argument("--run-id", required=True, type=validate_run_id)
    preflight.add_argument("--wrapper-repo", type=Path, default=Path("."))
    preflight.add_argument("--controlled-source-repo", type=Path, required=True)
    preflight.add_argument("--controlled-source-ref", required=True)
    preflight.add_argument("--run-root-policy", choices=("fresh", "reuse"), default="fresh")
    preflight.add_argument("--output", type=Path, help="optional JSON output path")
    preflight.add_argument("--stage-output", type=Path, help="optional stage JSON output path")
    preflight.set_defaults(func=_cmd_preflight)

    workspace = subparsers.add_parser(
        "prepare-workspace", help="prepare separated run and provenance workspaces"
    )
    workspace.add_argument("--config", type=Path, default=Path("configs/run.synthetic.yaml"))
    workspace.add_argument("--run-id", required=True, type=validate_run_id)
    workspace.add_argument("--workspace-root", type=Path, default=Path("."))
    workspace.add_argument("--output", type=Path, help="optional JSON output path")
    workspace.add_argument("--stage-output", type=Path, help="optional stage JSON output path")
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

    stage_targets = subparsers.add_parser(
        "list-run-stage-targets",
        help="list configured Make targets for the Ansible run harness",
    )
    stage_targets.add_argument("--config", type=Path, default=Path("configs/run.synthetic.yaml"))
    stage_targets.add_argument("--format", choices=("json", "lines"), default="json")
    stage_targets.set_defaults(func=_cmd_list_run_stage_targets)

    mock_lsf = subparsers.add_parser("submit-mock-lsf", help="submit local async mock LSF job")
    mock_lsf.add_argument("--config", type=Path, default=Path("configs/run.synthetic.yaml"))
    mock_lsf.add_argument("--run-id", required=True, type=validate_run_id)
    mock_lsf.add_argument("--workspace-root", type=Path, default=Path("."))
    mock_lsf.add_argument("--controlled-source-repo", type=Path, required=True)
    mock_lsf.add_argument("--output", type=Path, help="optional scheduler YAML output path")
    mock_lsf.add_argument("--stage-output", type=Path, help="optional stage JSON output path")
    mock_lsf.set_defaults(func=_cmd_submit_mock_lsf)

    wait_mock_lsf = subparsers.add_parser("wait-mock-lsf", help="wait for mock LSF job")
    wait_mock_lsf.add_argument("--config", type=Path, default=Path("configs/run.synthetic.yaml"))
    wait_mock_lsf.add_argument("--run-id", required=True, type=validate_run_id)
    wait_mock_lsf.add_argument("--workspace-root", type=Path, default=Path("."))
    wait_mock_lsf.add_argument("--output", type=Path, help="optional job-state JSON output path")
    wait_mock_lsf.add_argument("--stage-output", type=Path, help="optional stage JSON output path")
    wait_mock_lsf.set_defaults(func=_cmd_wait_mock_lsf)

    collect_mock_lsf = subparsers.add_parser(
        "collect-mock-lsf", help="collect mock LSF accounting evidence"
    )
    collect_mock_lsf.add_argument("--config", type=Path, default=Path("configs/run.synthetic.yaml"))
    collect_mock_lsf.add_argument("--run-id", required=True, type=validate_run_id)
    collect_mock_lsf.add_argument("--workspace-root", type=Path, default=Path("."))
    collect_mock_lsf.add_argument(
        "--output", type=Path, help="optional accounting YAML output path"
    )
    collect_mock_lsf.add_argument(
        "--stage-output", type=Path, help="optional stage JSON output path"
    )
    collect_mock_lsf.set_defaults(func=_cmd_collect_mock_lsf)

    run_simulation = subparsers.add_parser(
        "run-simulation", help="execute the controlled synthetic simulation stage"
    )
    run_simulation.add_argument("--config", type=Path, default=Path("configs/run.synthetic.yaml"))
    run_simulation.add_argument("--run-id", required=True, type=validate_run_id)
    run_simulation.add_argument("--workspace-root", type=Path, default=Path("."))
    run_simulation.add_argument("--controlled-source-repo", type=Path, required=True)
    run_simulation.add_argument(
        "--stage-output",
        "--output",
        dest="output",
        type=Path,
        help="optional stage JSON output path",
    )
    run_simulation.set_defaults(func=_cmd_run_simulation)

    extract_required = subparsers.add_parser(
        "extract-required", help="execute the controlled required extraction stage"
    )
    extract_required.add_argument("--config", type=Path, default=Path("configs/run.synthetic.yaml"))
    extract_required.add_argument("--run-id", required=True, type=validate_run_id)
    extract_required.add_argument("--workspace-root", type=Path, default=Path("."))
    extract_required.add_argument("--controlled-source-repo", type=Path, required=True)
    extract_required.add_argument(
        "--stage-output",
        "--output",
        dest="output",
        type=Path,
        help="optional stage JSON output path",
    )
    extract_required.set_defaults(func=_cmd_extract_required)

    extract_ad_hoc = subparsers.add_parser(
        "extract-ad-hoc", help="execute the controlled ad hoc extraction stage"
    )
    extract_ad_hoc.add_argument("--config", type=Path, default=Path("configs/run.synthetic.yaml"))
    extract_ad_hoc.add_argument("--run-id", required=True, type=validate_run_id)
    extract_ad_hoc.add_argument("--workspace-root", type=Path, default=Path("."))
    extract_ad_hoc.add_argument("--controlled-source-repo", type=Path, required=True)
    extract_ad_hoc.add_argument(
        "--stage-output",
        "--output",
        dest="output",
        type=Path,
        help="optional stage JSON output path",
    )
    extract_ad_hoc.set_defaults(func=_cmd_extract_ad_hoc)

    build_reports = subparsers.add_parser(
        "build-reports", help="generate minimal XLSX, PNG, and PPTX report products"
    )
    build_reports.add_argument("--config", type=Path, default=Path("configs/run.synthetic.yaml"))
    build_reports.add_argument("--run-id", required=True, type=validate_run_id)
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
    inventory_pre.add_argument("--run-id", required=True, type=validate_run_id)
    inventory_pre.add_argument("--workspace-root", type=Path, default=Path("."))
    inventory_pre.add_argument("--inputs-output", type=Path)
    inventory_pre.add_argument("--scripts-output", type=Path)
    inventory_pre.add_argument("--stage-output", type=Path, help="optional stage JSON output path")
    inventory_pre.set_defaults(func=_cmd_inventory_pre)

    inventory_post = subparsers.add_parser(
        "inventory-post", help="write post-run raw-output and derived-product inventories"
    )
    inventory_post.add_argument("--config", type=Path, default=Path("configs/run.synthetic.yaml"))
    inventory_post.add_argument("--run-id", required=True, type=validate_run_id)
    inventory_post.add_argument("--workspace-root", type=Path, default=Path("."))
    inventory_post.add_argument("--raw-output", type=Path)
    inventory_post.add_argument("--products-output", type=Path)
    inventory_post.add_argument("--stage-output", type=Path, help="optional stage JSON output path")
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

    validate_required = subparsers.add_parser(
        "validate-required", help="validate the configured required CSV product"
    )
    validate_required.add_argument("--shape-config", type=Path, required=True)
    validate_required.add_argument("--run-id", required=True, type=validate_run_id)
    validate_required.add_argument("--workspace-root", type=Path, default=Path("."))
    validate_required.add_argument(
        "--stage-output", type=Path, help="optional stage JSON output path"
    )
    validate_required.set_defaults(func=_cmd_validate_required)

    assemble = subparsers.add_parser("assemble-manifest", help="assemble manifest YAML")
    assemble.add_argument("input", type=Path, help="YAML mapping of manifest assembly fields")
    assemble.add_argument("--output", type=Path, required=True, help="manifest YAML output path")
    assemble.set_defaults(func=_cmd_assemble_manifest)

    assemble_run = subparsers.add_parser(
        "assemble-run-manifest", help="assemble a run manifest from workflow evidence files"
    )
    assemble_run.add_argument("--config", type=Path, default=Path("configs/run.synthetic.yaml"))
    assemble_run.add_argument("--run-id", required=True, type=validate_run_id)
    assemble_run.add_argument("--workspace-root", type=Path, default=Path("."))
    assemble_run.add_argument("--controlled-source-repo", type=Path, required=True)
    assemble_run.add_argument("--controlled-source-ref", required=True)
    assemble_run.add_argument(
        "--output", type=Path, required=True, help="manifest YAML output path"
    )
    assemble_run.add_argument("--stage-output", type=Path, help="optional stage JSON output path")
    assemble_run.set_defaults(func=_cmd_assemble_run_manifest)

    smoke = subparsers.add_parser("smoke-manifest", help="smoke-validate manifest sections")
    smoke.add_argument("manifest", type=Path)
    smoke.add_argument("--output", type=Path, help="optional JSON output path")
    smoke.add_argument("--config", type=Path, default=Path("configs/run.synthetic.yaml"))
    smoke.add_argument("--run-id", type=validate_run_id)
    smoke.add_argument("--workspace-root", type=Path, default=Path("."))
    smoke.add_argument("--controlled-source-repo", type=Path)
    smoke.add_argument("--controlled-source-ref")
    smoke.add_argument("--stage-output", type=Path, help="optional stage JSON output path")
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
    started_at = _utc_now()
    if args.run_root_policy == "fresh":
        _ensure_fresh_run_root(args.config, args.wrapper_repo, args.run_id)
    result = run_preflight(
        config_path=args.config,
        wrapper_repo=args.wrapper_repo,
        controlled_source_repo=args.controlled_source_repo,
        controlled_source_ref=args.controlled_source_ref,
        run_id=args.run_id,
    )
    finished_at = _utc_now()
    _write_json(result.to_dict(), args.output)
    _write_support_stage_attempt(
        args,
        "preflight",
        started_at=started_at,
        finished_at=finished_at,
        controlled_source_repo=args.controlled_source_repo,
    )
    return 0


def _ensure_fresh_run_root(config_path: Path, workspace_root: Path, run_id: str) -> None:
    config = read_config_mapping(config_path)
    layout = _required_mapping(config, "layout")
    run_root_template = _required_string(layout, "run_root")
    run_root = Path(workspace_root).expanduser().resolve() / run_root_template.format(run_id=run_id)
    if run_root.exists():
        raise ValueError(
            f"run root already exists for run_id {run_id!r}: {run_root.as_posix()}; "
            "choose a fresh run_id or set RUN_ROOT_POLICY=reuse for focused debugging"
        )


def _cmd_prepare_workspace(args: argparse.Namespace) -> int:
    with _support_stage_attempt(args, "prepare_workspace"):
        result = prepare_workspace(
            config_path=args.config,
            run_id=args.run_id,
            workspace_root=args.workspace_root,
        )
        _write_json(result.to_dict(), args.output)
    return 0


def _cmd_materialize_inputs(args: argparse.Namespace) -> int:
    with _support_stage_attempt(
        args, "materialize_inputs", controlled_source_repo=args.controlled_source_repo
    ):
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
    with _support_stage_attempt(
        args, "materialize_procs", controlled_source_repo=args.controlled_source_repo
    ):
        result = materialize_runtime_scripts(
            config_path=args.config,
            run_id=args.run_id,
            controlled_source_repo=args.controlled_source_repo,
            controlled_source_ref=args.controlled_source_ref,
            workspace_root=args.workspace_root,
        )
        _write_json(result.to_dict(), args.output)
    return 0


def _cmd_list_run_stage_targets(args: argparse.Namespace) -> int:
    targets = configured_harness_make_targets(args.config)
    if args.format == "lines":
        for target in targets:
            print(target)
    else:
        _write_json(list(targets), None)
    return 0


def _cmd_submit_mock_lsf(args: argparse.Namespace) -> int:
    with _support_stage_attempt(args, "submit_mock_lsf"):
        payload = submit_mock_lsf_job(
            config_path=args.config,
            run_id=args.run_id,
            workspace_root=args.workspace_root,
            controlled_source_repo=args.controlled_source_repo,
            output=args.output,
        )
        _write_json(payload, None)
    return 0


def _cmd_wait_mock_lsf(args: argparse.Namespace) -> int:
    with _support_stage_attempt(args, "wait_mock_lsf") as attempt:
        payload = wait_mock_lsf_job(
            config_path=args.config,
            run_id=args.run_id,
            workspace_root=args.workspace_root,
        )
        _write_json(payload, args.output)
        status = "pass" if payload.get("state") == "DONE" else "fail"
        if status == "fail":
            attempt.fail(f"scheduler reached {payload.get('state')!r}")
    return 0 if status == "pass" else 1


def _cmd_collect_mock_lsf(args: argparse.Namespace) -> int:
    with _support_stage_attempt(args, "collect_mock_lsf") as attempt:
        payload = collect_mock_lsf_accounting(
            config_path=args.config,
            run_id=args.run_id,
            workspace_root=args.workspace_root,
            output=args.output,
        )
        _write_json(payload, None)
        status = "pass" if payload.get("state") == "DONE" else "fail"
        if status == "fail":
            attempt.fail(f"scheduler accounting recorded {payload.get('state')!r}")
    return 0 if status == "pass" else 1


def _cmd_run_simulation(args: argparse.Namespace) -> int:
    result = run_synthetic_simulation(
        config_path=args.config,
        run_id=args.run_id,
        workspace_root=args.workspace_root,
        controlled_source_repo=args.controlled_source_repo,
    )
    _write_json(
        _with_evidence_path(result.to_dict(), args.output, args.workspace_root), args.output
    )
    return 0 if result.status == "pass" else 1


def _cmd_extract_required(args: argparse.Namespace) -> int:
    with _support_stage_attempt(
        args,
        "extract_required",
        controlled_source_repo=args.controlled_source_repo,
        record_success=False,
    ):
        result = run_required_extraction(
            config_path=args.config,
            run_id=args.run_id,
            workspace_root=args.workspace_root,
            controlled_source_repo=args.controlled_source_repo,
        )
        _write_json(
            _with_evidence_path(result.to_dict(), args.output, args.workspace_root), args.output
        )
    return 0 if result.status == "pass" else 1


def _cmd_extract_ad_hoc(args: argparse.Namespace) -> int:
    with _support_stage_attempt(
        args,
        "extract_ad_hoc",
        controlled_source_repo=args.controlled_source_repo,
        record_success=False,
    ):
        result = run_ad_hoc_extraction(
            config_path=args.config,
            run_id=args.run_id,
            workspace_root=args.workspace_root,
            controlled_source_repo=args.controlled_source_repo,
        )
        _write_json(
            _with_evidence_path(result.to_dict(), args.output, args.workspace_root), args.output
        )
    return 0 if result.status == "pass" else 1


def _cmd_build_reports(args: argparse.Namespace) -> int:
    with _support_stage_attempt(args, "build_reports"):
        records = build_report_product_evidence(
            run_id=args.run_id, workspace_root=args.workspace_root
        )
        _write_json(list(records), args.output)
    return 0


def _write_report_stage_evidence(
    *,
    config_path: Path,
    run_id: str,
    workspace_root: Path,
    output: Path,
    products: Sequence[dict[str, str | int | None]],
    started_at: datetime,
    finished_at: datetime,
) -> None:
    root = workspace_root.expanduser().resolve()
    provenance_root = root / "runs" / run_id / "provenance"
    log_root = provenance_root / "logs"
    log_root.mkdir(parents=True, exist_ok=True)
    stdout_log = log_root / "build_reports.stdout.log"
    stderr_log = log_root / "build_reports.stderr.log"
    stdout_log.write_text("Generated report products.\n", encoding="utf-8")
    stderr_log.write_text("", encoding="utf-8")
    payload = stage_attempt_evidence(
        config_path=config_path,
        run_id=run_id,
        stage_name="build_reports",
        workspace_root=root,
        started_at=started_at,
        finished_at=finished_at,
        evidence_path=output,
    )
    payload["outputs"] = list(products)
    _write_json(payload, output)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _write_support_stage_attempt(
    args: argparse.Namespace,
    stage_name: str,
    *,
    started_at: datetime,
    finished_at: datetime,
    controlled_source_repo: Path | None = None,
    status: str = "pass",
    return_code: int | None = 0,
    error: BaseException | None = None,
    evidence: dict[str, Any] | None = None,
) -> None:
    output = getattr(args, "stage_output", None)
    if output is None:
        return
    payload = stage_attempt_evidence(
        config_path=getattr(args, "config", Path("configs/run.synthetic.yaml")),
        run_id=args.run_id,
        stage_name=stage_name,
        workspace_root=getattr(args, "workspace_root", Path(".")),
        controlled_source_repo=controlled_source_repo,
        started_at=started_at,
        finished_at=finished_at,
        status=status,
        return_code=return_code,
        evidence_path=output,
    )
    if error is not None:
        payload["error"] = {
            "type": type(error).__name__,
            "message": str(error),
        }
    if evidence is not None:
        payload.update(evidence)
    _write_json(payload, output)


@contextmanager
def _support_stage_attempt(
    args: argparse.Namespace,
    stage_name: str,
    *,
    controlled_source_repo: Path | None = None,
    record_success: bool = True,
) -> Iterator["_SupportAttemptOutcome"]:
    """Record one support-stage attempt without changing operation failure behavior."""

    started_at = _utc_now()
    outcome = _SupportAttemptOutcome()
    try:
        yield outcome
    except Exception as error:
        try:
            _write_support_stage_attempt(
                args,
                stage_name,
                started_at=started_at,
                finished_at=_utc_now(),
                controlled_source_repo=controlled_source_repo,
                status="fail",
                return_code=1,
                error=error,
                evidence=outcome.evidence,
            )
        except Exception as evidence_error:
            error.add_note(f"failed to record {stage_name} attempt evidence: {evidence_error}")
        raise
    else:
        if not record_success and outcome.status == "pass":
            return
        _write_support_stage_attempt(
            args,
            stage_name,
            started_at=started_at,
            finished_at=_utc_now(),
            controlled_source_repo=controlled_source_repo,
            status=outcome.status,
            return_code=outcome.return_code,
            error=outcome.error,
            evidence=outcome.evidence,
        )


@dataclass
class _SupportAttemptOutcome:
    status: str = "pass"
    return_code: int = 0
    error: BaseException | None = None
    evidence: dict[str, Any] = field(default_factory=dict)

    def fail(self, message: str, *, return_code: int = 1) -> None:
        self.status = "fail"
        self.return_code = return_code
        self.error = RuntimeError(message)


def _with_evidence_path(
    payload: dict[str, Any], output: Path | None, workspace_root: Path
) -> dict[str, Any]:
    if output is None:
        return payload
    root = workspace_root.expanduser().resolve()
    resolved = output if output.is_absolute() else root / output
    payload["evidence_path"] = (
        resolved.relative_to(root).as_posix()
        if resolved.is_relative_to(root)
        else resolved.as_posix()
    )
    return payload


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
    with _support_stage_attempt(args, "inventory_pre"):
        return _run_inventory_pre(args)


def _run_inventory_pre(args: argparse.Namespace) -> int:
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
    scripts.extend(
        _run_local_controlled_code_records(inventory_root / "materialized_runtime_scripts.json")
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
    with _support_stage_attempt(args, "inventory_post"):
        return _run_inventory_post(args)


def _run_inventory_post(args: argparse.Namespace) -> int:
    root = args.workspace_root.expanduser().resolve()
    run_root = root / "runs" / args.run_id
    sim_root = run_root / "sim-run-root"
    provenance_root = run_root / "provenance"
    inventory_root = provenance_root / "inventories"
    raw_output = args.raw_output or inventory_root / "post_run_raw_outputs.json"
    products_output = args.products_output or inventory_root / "post_run_derived_products.json"
    config = read_config_mapping(args.config)

    raw_outputs = _post_run_raw_output_records(root=root, run_root=run_root, sim_root=sim_root)
    products = _post_run_derived_product_records(
        root=root,
        run_root=run_root,
        provenance_root=provenance_root,
        producing_stages=_producing_stages_by_output(config),
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


def _run_local_controlled_code_records(materialization_evidence: Path) -> list[dict[str, Any]]:
    loaded = json.loads(materialization_evidence.read_text(encoding="utf-8"))
    artifacts = loaded.get("artifacts") if isinstance(loaded, dict) else None
    if not isinstance(artifacts, list):
        raise ValueError(
            f"materialization evidence artifacts must be a list: {materialization_evidence}"
        )
    records: list[dict[str, Any]] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict) or artifact.get("role") != "controlled_code":
            continue
        destination = artifact.get("destination_path")
        if not isinstance(destination, str) or not destination:
            raise ValueError(
                f"controlled-code destination path is missing: {materialization_evidence}"
            )
        record = dict(artifact)
        record["run_relative_path"] = destination
        marker = "/provenance/"
        record["relative_path"] = (
            f"provenance/{destination.split(marker, maxsplit=1)[1]}"
            if marker in destination
            else destination
        )
        records.append(record)
    return records


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
    *,
    root: Path,
    run_root: Path,
    provenance_root: Path,
    producing_stages: dict[str, str],
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
        entry["producing_stage"] = producing_stages.get(entry["workflow_relative_path"])
        payload.append(entry)
    return payload


def _producing_stages_by_output(config: dict[str, Any]) -> dict[str, str]:
    stages = config.get("stages")
    if not isinstance(stages, list):
        raise ValueError("stages must be a list")
    producing_stages: dict[str, str] = {}
    for index, raw_stage in enumerate(stages):
        if not isinstance(raw_stage, dict):
            raise ValueError(f"stages[{index}] must be a mapping")
        stage_name = raw_stage.get("name")
        outputs = raw_stage.get("outputs", [])
        if not isinstance(stage_name, str) or not isinstance(outputs, list):
            continue
        for output in outputs:
            if isinstance(output, str) and output.startswith("provenance/products/"):
                producing_stages[output] = stage_name
    return producing_stages


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
    parser.add_argument("--run-id", required=True, type=validate_run_id)
    parser.add_argument("--workspace-root", type=Path, default=Path("."))
    parser.add_argument("--controlled-source-repo", type=Path, required=True)
    parser.add_argument("--controlled-source-ref", required=True)
    parser.add_argument("--output", type=Path, help="optional JSON output path")
    parser.add_argument("--stage-output", type=Path, help="optional stage JSON output path")


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


def _cmd_validate_required(args: argparse.Namespace) -> int:
    with _support_stage_attempt(args, "validate") as attempt:
        return _run_validate_required(args, attempt)


def _run_validate_required(args: argparse.Namespace, attempt: _SupportAttemptOutcome) -> int:
    shape = read_config_mapping(args.shape_config)
    run_root = args.workspace_root.expanduser().resolve() / "runs" / args.run_id
    product = _required_mapping(shape, "product")
    expectations = _required_mapping(shape, "expectations")
    evidence_config = _required_mapping(shape, "evidence")

    product_path = run_root / _required_string(product, "relative_path")
    validation_name = product.get("name", "required_extract")
    if not isinstance(validation_name, str) or not validation_name:
        raise ValueError("product.name must be a non-empty string when configured")
    output_path = run_root / _required_string(evidence_config, "output_path")
    header_value = expectations.get("expected_header")
    if not isinstance(header_value, list) or not all(
        isinstance(value, str) for value in header_value
    ):
        raise ValueError(
            "expected_shape required_extract expectations.expected_header must be a list of strings"
        )
    expected_values_raw = expectations.get("expected_column_values", {})
    if not isinstance(expected_values_raw, dict) or not all(
        isinstance(column, str)
        and isinstance(values, list)
        and all(isinstance(value, str) for value in values)
        for column, values in expected_values_raw.items()
    ):
        raise ValueError("expectations.expected_column_values must map columns to string lists")
    integer_columns_raw = expectations.get("integer_columns", [])
    if not isinstance(integer_columns_raw, list) or not all(
        isinstance(value, str) for value in integer_columns_raw
    ):
        raise ValueError("expectations.integer_columns must be a list of strings")

    evidence = validate_csv_product(
        product_path,
        CSVShapeExpectation(
            expected_data_rows=_optional_int(expectations, "expected_data_rows"),
            minimum_data_rows=_optional_int(expectations, "minimum_data_rows"),
            expected_column_count=_optional_int(expectations, "expected_column_count"),
            expected_header=tuple(header_value),
            expected_column_values={
                str(column): tuple(values) for column, values in expected_values_raw.items()
            },
            integer_columns=tuple(integer_columns_raw),
        ),
        display_path=_required_string(product, "display_path"),
    )
    _write_json(evidence.to_dict(), output_path)
    _write_json(
        {
            "status": evidence.status.value,
            "validation": validation_name,
            "product": product_path.as_posix(),
            "evidence": output_path.as_posix(),
        },
        None,
    )
    if not evidence.passed:
        attempt.fail("required extract validation failed")
    return 0 if evidence.passed else 1


def _cmd_assemble_manifest(args: argparse.Namespace) -> int:
    source = _read_yaml_mapping(args.input)
    manifest = assemble_manifest(ManifestAssemblyInput(**source))
    write_manifest(manifest, args.output)
    _write_json({"status": "pass", "manifest": args.output.as_posix()}, None)
    return 0


def _cmd_assemble_run_manifest(args: argparse.Namespace) -> int:
    with _support_stage_attempt(
        args, "manifest", controlled_source_repo=args.controlled_source_repo
    ) as attempt:
        result = _run_assemble_run_manifest(args)
        attempt.evidence.update(
            {
                "manifest": args.output.as_posix(),
                "manifest_sha256": sha256_file(args.output),
            }
        )
        return result


def _run_assemble_run_manifest(args: argparse.Namespace) -> int:
    manifest = assemble_run_manifest(
        config_path=args.config,
        run_id=args.run_id,
        workspace_root=args.workspace_root,
        controlled_source_repo=args.controlled_source_repo,
        controlled_source_ref=args.controlled_source_ref,
    )
    write_manifest(manifest, args.output)
    _write_json({"status": "pass", "manifest": args.output.as_posix()}, None)
    return 0


def _cmd_smoke_manifest(args: argparse.Namespace) -> int:
    if args.run_id is None or args.stage_output is None:
        return _run_smoke_manifest(args, None)
    with _support_stage_attempt(
        args, "manifest_smoke", controlled_source_repo=args.controlled_source_repo
    ) as attempt:
        return _run_smoke_manifest(args, attempt)


def _run_smoke_manifest(args: argparse.Namespace, attempt: _SupportAttemptOutcome | None) -> int:
    manifest = _read_yaml_mapping(args.manifest)
    missing = missing_required_sections(manifest)
    missing_key_values = missing_required_key_values(manifest)
    manifest_sha256 = sha256_file(args.manifest)
    assembly_receipt_path: Path | None = None
    assembly_manifest_sha256: str | None = None
    semantic_errors: list[str] = []
    if args.run_id is not None and args.stage_output is not None:
        semantic_errors.extend(
            semantic_consistency_errors(
                manifest,
                config_path=args.config,
                workspace_root=args.workspace_root,
            )
        )
        stage_output = args.stage_output
        if not isinstance(stage_output, Path):
            raise ValueError("manifest smoke stage output must be a path")
        assembly_receipt_path = stage_output.with_name("manifest.stage.json")
        try:
            assembly_receipt = json.loads(assembly_receipt_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            semantic_errors.append(f"manifest assembly receipt cannot be read: {error}")
        else:
            if not isinstance(assembly_receipt, dict):
                semantic_errors.append("manifest assembly receipt must be a mapping")
            else:
                recorded_hash = assembly_receipt.get("manifest_sha256")
                assembly_manifest_sha256 = recorded_hash if isinstance(recorded_hash, str) else None
                if assembly_manifest_sha256 != manifest_sha256:
                    semantic_errors.append(
                        "manifest SHA-256 does not match external assembly receipt"
                    )
    passed = not missing and not missing_key_values and not semantic_errors
    payload = {
        "status": "pass" if passed else "fail",
        "manifest": args.manifest.as_posix(),
        "manifest_sha256": manifest_sha256,
        "assembly_receipt": (
            assembly_receipt_path.as_posix() if assembly_receipt_path is not None else None
        ),
        "assembly_manifest_sha256": assembly_manifest_sha256,
        "manifest_hash_matches_assembly_receipt": (
            assembly_manifest_sha256 == manifest_sha256
            if assembly_receipt_path is not None
            else None
        ),
        "missing_required_sections": list(missing),
        "missing_required_key_values": list(missing_key_values),
        "semantic_errors": semantic_errors,
    }
    _write_json(payload, args.output)
    if attempt is not None:
        attempt.evidence.update(
            {
                "manifest": args.manifest.as_posix(),
                "manifest_sha256": manifest_sha256,
                "assembly_receipt": assembly_receipt_path.as_posix()
                if assembly_receipt_path is not None
                else None,
                "manifest_hash_matches_assembly_receipt": (
                    assembly_manifest_sha256 == manifest_sha256
                ),
            }
        )
    if not passed and attempt is not None:
        attempt.fail("manifest smoke validation failed")
    return 0 if passed else 1


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
    return read_yaml_mapping(path)


def _required_mapping(source: dict[str, Any], key: str) -> dict[str, Any]:
    value = source.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"expected_shape required_extract {key} must be a mapping")
    return value


def _required_string(source: dict[str, Any], key: str) -> str:
    value = source.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"expected_shape required_extract {key} must be a non-empty string")
    return value


def _optional_int(source: dict[str, Any], key: str) -> int | None:
    value = source.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise ValueError(f"expected_shape required_extract {key} must be an integer")
    return value


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
