from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml

from provenance.cli import main
from provenance.scheduler import write_mock_lsf_metadata
from provenance.stages import (
    _stage_command_argv,
    run_ad_hoc_extraction,
    run_required_extraction,
    run_synthetic_simulation,
)
from provenance.workspace import materialize_inputs, prepare_workspace


def _write_config(path: Path) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "0.1",
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
                "stages": [
                    {
                        "name": "run_simulation",
                        "display_name": "Run simulation",
                        "lifecycle_class": "factory",
                        "display_order": 60,
                        "operator_visible": True,
                        "command": "procs/run-script.sh",
                        "command_kind": "materialized_controlled_script",
                        "working_directory": "sim-run-root",
                        "inputs": ["sim-run-root/input"],
                        "outputs": ["sim-run-root/lists/dirC/sim-out.dat"],
                    },
                    {
                        "name": "extract_required",
                        "display_name": "Extract required results",
                        "lifecycle_class": "factory",
                        "display_order": 70,
                        "operator_visible": True,
                        "command": (
                            "scripts/extract_required.pl sim-run-root/lists/dirC/sim-out.dat "
                            "provenance/products/extracted/required.csv"
                        ),
                        "working_directory": "controlled_source_repo",
                        "command_kind": "controlled_source_script",
                        "inputs": ["sim-run-root/lists/dirC/sim-out.dat"],
                        "outputs": ["provenance/products/extracted/required.csv"],
                    },
                    {
                        "name": "extract_ad_hoc",
                        "display_name": "Extract ad hoc results",
                        "lifecycle_class": "factory",
                        "display_order": 80,
                        "operator_visible": True,
                        "command": (
                            "scripts/ad_hoc_extract.py sim-run-root/lists/dirC/sim-out.dat "
                            "provenance/products/extracted/ad_hoc.csv"
                        ),
                        "working_directory": "controlled_source_repo",
                        "command_kind": "controlled_source_script",
                        "inputs": ["sim-run-root/lists/dirC/sim-out.dat"],
                        "outputs": ["provenance/products/extracted/ad_hoc.csv"],
                    },
                ],
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


def test_stage_command_argv_resolves_only_controlled_source_script_executables(
    tmp_path: Path,
) -> None:
    controlled_root = tmp_path / "controlled-source-demo"
    controlled_script = controlled_root / "scripts" / "extract_required.pl"
    controlled_script.parent.mkdir(parents=True)
    controlled_script.write_text("#!/usr/bin/env perl\n", encoding="utf-8")

    argv = _stage_command_argv(
        "scripts/extract_required.pl sim-run-root/lists/dirC/sim-out.dat provenance/out.csv",
        {"command_kind": "controlled_source_script"},
        controlled_root,
        tmp_path / "runs" / "demo_001",
        controlled_root,
    )

    assert argv[0] == controlled_script.as_posix()
    assert argv[1] == (tmp_path / "runs/demo_001/sim-run-root/lists/dirC/sim-out.dat").as_posix()
    assert argv[2] == (tmp_path / "runs/demo_001/provenance/out.csv").as_posix()


def test_stage_command_argv_does_not_fallback_to_controlled_root_for_materialized_stage(
    tmp_path: Path,
) -> None:
    controlled_root = tmp_path / "controlled-source-demo"
    controlled_script = controlled_root / "procs" / "run-script.sh"
    controlled_script.parent.mkdir(parents=True)
    controlled_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

    argv = _stage_command_argv(
        "procs/run-script.sh",
        {"command_kind": "materialized_controlled_script"},
        tmp_path / "runs" / "demo_001" / "sim-run-root",
        tmp_path / "runs" / "demo_001",
        controlled_root,
    )

    assert argv == ["procs/run-script.sh"]


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


def test_run_synthetic_simulation_writes_raw_output_and_stage_evidence(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="demo_007", workspace_root=tmp_path)
    materialize_inputs(
        config_path=config_path,
        run_id="demo_007",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
        controlled_source_ref="controlled-source-demo-v0.1.0",
    )
    assert (
        main(
            [
                "materialize-procs",
                "--config",
                str(config_path),
                "--run-id",
                "demo_007",
                "--workspace-root",
                str(tmp_path),
                "--controlled-source-repo",
                str(controlled_repo),
                "--controlled-source-ref",
                "controlled-source-demo-v0.1.0",
            ]
        )
        == 0
    )

    result = run_synthetic_simulation(
        config_path=config_path,
        run_id="demo_007",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
    )

    raw_output = tmp_path / "runs/demo_007/sim-run-root/lists/dirC/sim-out.dat"
    assert raw_output.is_file()
    assert raw_output.read_text(encoding="utf-8").splitlines()[0] == (
        "logical_group,example,bytes,sha256_prefix"
    )
    assert result.status == "pass"
    assert result.return_code == 0
    assert result.working_directory == "runs/demo_007/sim-run-root"
    assert result.stdout_log == "runs/demo_007/provenance/logs/run_simulation.stdout.log"
    assert result.stderr_log == "runs/demo_007/provenance/logs/run_simulation.stderr.log"
    assert result.started_at.endswith("Z")
    assert result.finished_at.endswith("Z")
    assert result.duration_seconds >= 0
    output = result.outputs[0]
    assert output.relative_path == "sim-run-root/lists/dirC/sim-out.dat"
    assert output.sim_area == "lists"
    assert output.logical_group == "dirC"
    assert output.role == "raw_output"
    assert output.sha256 is not None and len(output.sha256) == 64


def test_required_extraction_writes_derived_csv_outside_sim_run_root_and_stage_evidence(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="demo_008", workspace_root=tmp_path)
    materialize_inputs(
        config_path=config_path,
        run_id="demo_008",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
        controlled_source_ref="controlled-source-demo-v0.1.0",
    )
    main(
        [
            "materialize-procs",
            "--config",
            str(config_path),
            "--run-id",
            "demo_008",
            "--workspace-root",
            str(tmp_path),
            "--controlled-source-repo",
            str(controlled_repo),
            "--controlled-source-ref",
            "controlled-source-demo-v0.1.0",
        ]
    )
    run_synthetic_simulation(
        config_path=config_path,
        run_id="demo_008",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
    )

    result = run_required_extraction(
        config_path=config_path,
        run_id="demo_008",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
    )

    required_csv = tmp_path / "runs/demo_008/provenance/products/extracted/required.csv"
    assert required_csv.is_file()
    assert not (tmp_path / "runs/demo_008/sim-run-root/provenance").exists()
    assert required_csv.read_text(encoding="utf-8").splitlines() == [
        "logical_group,example,bytes,sha256_prefix",
        "dirC,ex1.dat,13,eebd9e4163d9",
        "dirC,ex2.dat,13,3a5f7839e322",
        "dirC,ex3.dat,13,6300c7d48a99",
    ]
    assert result.status == "pass"
    assert result.return_code == 0
    assert result.working_directory == "controlled-source-demo"
    assert result.stdout_log == "runs/demo_008/provenance/logs/extract_required.stdout.log"
    assert result.to_dict()["return_code"] == 0
    assert result.to_dict()["logs"] == {
        "stdout": "runs/demo_008/provenance/logs/extract_required.stdout.log",
        "stderr": "runs/demo_008/provenance/logs/extract_required.stderr.log",
    }
    assert result.inputs[0].relative_path == "sim-run-root/lists/dirC/sim-out.dat"
    assert result.inputs[0].role == "raw_output"
    assert result.inputs[0].sha256 is not None
    output = result.outputs[0]
    assert output.relative_path == "provenance/products/extracted/required.csv"
    assert output.role == "extracted_product"
    assert output.sha256 is not None and len(output.sha256) == 64


def test_cli_extract_required_writes_stage_json(tmp_path: Path) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    output_path = tmp_path / "runs/demo_009/provenance/logs/extract_required.stage.json"
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="demo_009", workspace_root=tmp_path)
    raw_output = tmp_path / "runs/demo_009/sim-run-root/lists/dirC/sim-out.dat"
    raw_output.parent.mkdir(parents=True)
    raw_output.write_text(
        "logical_group,example,bytes,sha256_prefix\n"
        "dirA,ex1.dat,13,ignoredaaaaa\n"
        "dirC,ex1.dat,13,7fee469deaea\n",
        encoding="utf-8",
    )

    assert (
        main(
            [
                "extract-required",
                "--config",
                str(config_path),
                "--run-id",
                "demo_009",
                "--workspace-root",
                str(tmp_path),
                "--controlled-source-repo",
                str(controlled_repo),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    evidence = json.loads(output_path.read_text(encoding="utf-8"))
    assert evidence["name"] == "extract_required"
    assert evidence["status"] == "pass"
    assert evidence["return_code"] == 0
    assert evidence["started_at"].endswith("Z")
    assert evidence["finished_at"].endswith("Z")
    assert evidence["logs"]["stdout"] == "runs/demo_009/provenance/logs/extract_required.stdout.log"
    assert evidence["outputs"][0]["relative_path"] == "provenance/products/extracted/required.csv"
    assert (tmp_path / "runs/demo_009/provenance/products/extracted/required.csv").is_file()


def test_ad_hoc_extraction_writes_derived_csv_outside_sim_run_root_and_stage_evidence(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="demo_010", workspace_root=tmp_path)
    raw_output = tmp_path / "runs/demo_010/sim-run-root/lists/dirC/sim-out.dat"
    raw_output.parent.mkdir(parents=True)
    raw_output.write_text(
        "logical_group,example,bytes,sha256_prefix\n"
        "dirA,ex1.dat,11,ignoredaaaaa\n"
        "dirC,ex1.dat,13,7fee469deaea\n"
        "dirC,ex2.dat,17,ignoredbbbbb\n",
        encoding="utf-8",
    )

    result = run_ad_hoc_extraction(
        config_path=config_path,
        run_id="demo_010",
        workspace_root=tmp_path,
        controlled_source_repo=controlled_repo,
    )

    ad_hoc_csv = tmp_path / "runs/demo_010/provenance/products/extracted/ad_hoc.csv"
    assert ad_hoc_csv.is_file()
    assert not (tmp_path / "runs/demo_010/sim-run-root/provenance").exists()
    assert ad_hoc_csv.read_text(encoding="utf-8").splitlines() == [
        "logical_group,input_count,total_bytes",
        "dirA,1,11",
        "dirC,2,30",
    ]
    assert result.status == "pass"
    assert result.return_code == 0
    assert result.working_directory == "controlled-source-demo"
    assert result.stdout_log == "runs/demo_010/provenance/logs/extract_ad_hoc.stdout.log"
    assert result.inputs[0].relative_path == "sim-run-root/lists/dirC/sim-out.dat"
    assert result.inputs[0].role == "raw_output"
    assert result.inputs[0].sha256 is not None
    output = result.outputs[0]
    assert output.relative_path == "provenance/products/extracted/ad_hoc.csv"
    assert output.role == "extracted_product"
    assert output.sha256 is not None and len(output.sha256) == 64


def test_cli_extract_ad_hoc_writes_stage_json(tmp_path: Path) -> None:
    config_path = tmp_path / "run.synthetic.yaml"
    controlled_repo = _create_controlled_source_repo(tmp_path / "controlled-source-demo")
    output_path = tmp_path / "runs/demo_011/provenance/logs/extract_ad_hoc.stage.json"
    _write_config(config_path)
    prepare_workspace(config_path=config_path, run_id="demo_011", workspace_root=tmp_path)
    raw_output = tmp_path / "runs/demo_011/sim-run-root/lists/dirC/sim-out.dat"
    raw_output.parent.mkdir(parents=True)
    raw_output.write_text(
        "logical_group,example,bytes,sha256_prefix\n"
        "dirB,ex1.dat,19,ignoredaaaaa\n"
        "dirC,ex1.dat,23,ignoredbbbbb\n",
        encoding="utf-8",
    )

    assert (
        main(
            [
                "extract-ad-hoc",
                "--config",
                str(config_path),
                "--run-id",
                "demo_011",
                "--workspace-root",
                str(tmp_path),
                "--controlled-source-repo",
                str(controlled_repo),
                "--output",
                str(output_path),
            ]
        )
        == 0
    )

    evidence = json.loads(output_path.read_text(encoding="utf-8"))
    assert evidence["name"] == "extract_ad_hoc"
    assert evidence["outputs"][0]["relative_path"] == "provenance/products/extracted/ad_hoc.csv"
    assert (tmp_path / "runs/demo_011/provenance/products/extracted/ad_hoc.csv").is_file()


def _create_controlled_source_repo(path: Path) -> Path:
    (path / "fixtures/controlled_inputs").mkdir(parents=True)
    for group in ("dirA", "dirB", "dirC"):
        group_path = path / "fixtures/controlled_inputs" / group
        group_path.mkdir()
        for name in ("ex1.dat", "ex2.dat", "ex3.dat"):
            (group_path / name).write_text(f"{group},{name}\n", encoding="utf-8")
    (path / "procs").mkdir()
    run_script = path / "procs/run-script.sh"
    run_script.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "run_root=${1:-$(pwd -P)}\n"
        'exec "$SYNTHETIC_SIM_ENGINE" "$run_root"\n',
        encoding="utf-8",
    )
    run_script.chmod(0o755)
    (path / "scripts").mkdir()
    engine = path / "scripts/synthetic_sim_engine.sh"
    engine.write_text(
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        "run_root=${1:-$(pwd -P)}\n"
        "input_root=$run_root/input\n"
        "output_dir=$run_root/lists/dirC\n"
        'mkdir -p -- "$output_dir"\n'
        "output_file=$output_dir/sim-out.dat\n"
        "printf 'logical_group,example,bytes,sha256_prefix\\n' >\"$output_file\"\n"
        "for logical_group in dirA dirB dirC; do\n"
        "  for example in ex1.dat ex2.dat ex3.dat; do\n"
        "    input_file=$input_root/$logical_group/$example\n"
        "    byte_count=$(wc -c <\"$input_file\" | tr -d ' ')\n"
        "    sha_prefix=$(sha256sum \"$input_file\" | cut -d ' ' -f 1 | cut -c 1-12)\n"
        '    printf \'%s,%s,%s,%s\\n\' "$logical_group" "$example" '
        '"$byte_count" "$sha_prefix" >>"$output_file"\n'
        "  done\n"
        "done\n"
        "printf 'Wrote synthetic raw output: %s\\n' \"$output_file\"\n",
        encoding="utf-8",
    )
    engine.chmod(0o755)
    extractor = path / "scripts/extract_required.pl"
    extractor.write_text(
        "#!/usr/bin/env perl\n"
        "use strict;\n"
        "use warnings;\n"
        "my ($input_path, $output_path) = @ARGV;\n"
        "open my $in, '<', $input_path or die \"Cannot read $input_path: $!\\n\";\n"
        "open my $out, '>', $output_path or die \"Cannot write $output_path: $!\\n\";\n"
        "my $header = <$in>;\n"
        "chomp $header;\n"
        'print {$out} "$header\\n";\n'
        "while (my $line = <$in>) {\n"
        "  chomp $line;\n"
        "  my ($logical_group, $example, $bytes, $sha_prefix) = split /,/, $line;\n"
        "  next unless defined $logical_group && $logical_group eq 'dirC';\n"
        "  print {$out} join(',', $logical_group, $example, $bytes, $sha_prefix), \"\\n\";\n"
        "}\n",
        encoding="utf-8",
    )
    extractor.chmod(0o755)
    ad_hoc_extractor = path / "scripts/ad_hoc_extract.py"
    ad_hoc_extractor.write_text(
        "#!/usr/bin/env python3\n"
        "import csv\n"
        "import sys\n"
        "from collections import defaultdict\n"
        "from pathlib import Path\n"
        "input_path = Path(sys.argv[1])\n"
        "output_path = Path(sys.argv[2])\n"
        "totals = defaultdict(int)\n"
        "counts = defaultdict(int)\n"
        "with input_path.open(newline='', encoding='utf-8') as input_file:\n"
        "    reader = csv.DictReader(input_file)\n"
        "    for row in reader:\n"
        "        totals[row['logical_group']] += int(row['bytes'])\n"
        "        counts[row['logical_group']] += 1\n"
        "output_path.parent.mkdir(parents=True, exist_ok=True)\n"
        "with output_path.open('w', newline='', encoding='utf-8') as output_file:\n"
        "    writer = csv.DictWriter(\n"
        "        output_file, fieldnames=['logical_group', 'input_count', 'total_bytes']\n"
        "    )\n"
        "    writer.writeheader()\n"
        "    for logical_group in sorted(counts):\n"
        "        writer.writerow(\n"
        "            {\n"
        "                'logical_group': logical_group,\n"
        "                'input_count': counts[logical_group],\n"
        "                'total_bytes': totals[logical_group],\n"
        "            }\n"
        "        )\n",
        encoding="utf-8",
    )
    ad_hoc_extractor.chmod(0o755)
    _git(path, "init")
    _git(path, "add", "fixtures", "procs", "scripts")
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
