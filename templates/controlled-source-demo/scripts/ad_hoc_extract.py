#!/usr/bin/env python3
"""Minimal ad hoc extractor for later provenance stages."""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: ad_hoc_extract.py <sim-out.dat> <ad_hoc.csv>", file=sys.stderr)
        return 2

    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    totals: dict[str, int] = defaultdict(int)
    counts: dict[str, int] = defaultdict(int)
    with input_path.open(newline="", encoding="utf-8") as input_file:
        reader = csv.DictReader(input_file)
        expected = ["logical_group", "example", "bytes", "sha256_prefix"]
        if reader.fieldnames != expected:
            print(f"Unexpected header in {input_path}: {reader.fieldnames!r}", file=sys.stderr)
            return 1
        for row in reader:
            logical_group = row["logical_group"]
            totals[logical_group] += int(row["bytes"])
            counts[logical_group] += 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=["logical_group", "input_count", "total_bytes"])
        writer.writeheader()
        for logical_group in sorted(counts):
            writer.writerow(
                {
                    "logical_group": logical_group,
                    "input_count": counts[logical_group],
                    "total_bytes": totals[logical_group],
                }
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
