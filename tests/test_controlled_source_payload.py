from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_controlled_synthetic_engine_accepts_short_runtime_delay(tmp_path: Path) -> None:
    run_root = tmp_path / "sim-run-root"
    input_root = run_root / "input"
    for logical_group in ("dirA", "dirB", "dirC"):
        group_root = input_root / logical_group
        group_root.mkdir(parents=True)
        for example in ("ex1.dat", "ex2.dat", "ex3.dat"):
            (group_root / example).write_text(f"{logical_group}/{example}\n", encoding="utf-8")

    env = os.environ.copy()
    env["SYNTHETIC_SIM_RUNTIME_DELAY_SECONDS"] = "0.01"
    started = time.monotonic()
    completed = subprocess.run(
        [
            str(ROOT / "templates/controlled-source-demo/scripts/synthetic_sim_engine.sh"),
            str(run_root),
        ],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert time.monotonic() - started >= 0.01
    assert "Applying controlled synthetic runtime delay" in completed.stdout
    assert (run_root / "lists" / "dirC" / "sim-out.dat").is_file()


def test_controlled_extractors_publish_atomically_and_preserve_existing_on_failure(
    tmp_path: Path,
) -> None:
    raw_output = tmp_path / "sim-out.dat"
    raw_output.write_text(
        "logical_group,example,bytes,sha256_prefix\n"
        "dirA,ex1.dat,11,aaaaaaaaaaaa\n"
        "dirC,ex1.dat,13,bbbbbbbbbbbb\n",
        encoding="utf-8",
    )
    required = tmp_path / "required.csv"
    ad_hoc = tmp_path / "ad_hoc.csv"

    required_result = subprocess.run(
        [
            str(ROOT / "templates/controlled-source-demo/scripts/extract_required.pl"),
            str(raw_output),
            str(required),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    ad_hoc_result = subprocess.run(
        [
            str(ROOT / "templates/controlled-source-demo/scripts/ad_hoc_extract.py"),
            str(raw_output),
            str(ad_hoc),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert required_result.returncode == 0, required_result.stderr
    assert ad_hoc_result.returncode == 0, ad_hoc_result.stderr
    assert required.read_text(encoding="utf-8").splitlines()[-1].startswith("dirC,")
    assert ad_hoc.read_text(encoding="utf-8").splitlines()[-1] == "dirC,1,13"
    assert not list(tmp_path.glob(".required.csv.*"))
    assert not list(tmp_path.glob(".ad_hoc.csv.*"))

    raw_output.write_text("unexpected,header\n", encoding="utf-8")
    required.write_text("preserve required\n", encoding="utf-8")
    ad_hoc.write_text("preserve ad hoc\n", encoding="utf-8")
    failed_required = subprocess.run(
        [
            str(ROOT / "templates/controlled-source-demo/scripts/extract_required.pl"),
            str(raw_output),
            str(required),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    failed_ad_hoc = subprocess.run(
        [
            str(ROOT / "templates/controlled-source-demo/scripts/ad_hoc_extract.py"),
            str(raw_output),
            str(ad_hoc),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert failed_required.returncode != 0
    assert failed_ad_hoc.returncode != 0
    assert required.read_text(encoding="utf-8") == "preserve required\n"
    assert ad_hoc.read_text(encoding="utf-8") == "preserve ad hoc\n"
