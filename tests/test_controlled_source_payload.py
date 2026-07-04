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
