"""Command-line entry points for provenance helper operations.

The CLI is intentionally thin: it exposes the typed helper modules for Make,
Ansible, and tests without embedding orchestration policy. Commands write
JSON/YAML evidence to stdout by default, or to an explicit output path when one
is supplied.
"""

from __future__ import annotations

import argparse
import json
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
from provenance.inventory import inventory_files, with_sha256
from provenance.manifest import (
    ManifestAssemblyInput,
    assemble_manifest,
    missing_required_sections,
    write_manifest,
)
from provenance.validation import CSVShapeExpectation, validate_csv_product


def main(argv: Sequence[str] | None = None) -> int:
    """Run the provenance CLI and return a process exit code."""

    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (GitStateError, FileNotFoundError, NotADirectoryError, ValueError) as exc:
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

    inventory = subparsers.add_parser("inventory", help="inventory files under a root")
    inventory.add_argument("root", type=Path)
    inventory.add_argument("--with-hashes", action="store_true", help="include SHA-256 hashes")
    inventory.add_argument("--output", type=Path, help="optional JSON output path")
    inventory.set_defaults(func=_cmd_inventory)

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


def _cmd_inventory(args: argparse.Namespace) -> int:
    records = inventory_files(args.root)
    if args.with_hashes:
        records = tuple(
            with_sha256(record, hash_artifact(args.root / record.relative_path).sha256 or "")
            for record in records
        )
    _write_json([record.to_dict() for record in records], args.output)
    return 0


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
