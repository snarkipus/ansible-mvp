#!/usr/bin/env bash
set -euo pipefail

# Deterministic synthetic simulation engine for the provenance MVP.
# Input contract:  <run-root>/input/{dirA,dirB,dirC}/ex{1,2,3}.dat
# Output contract: <run-root>/lists/dirC/sim-out.dat

run_root=${1:-$(pwd -P)}
input_root=$run_root/input
output_dir=$run_root/lists/dirC
output_file=$output_dir/sim-out.dat
run_id=${SYNTHETIC_SIM_RUN_ID:-$(basename -- "$(dirname -- "$run_root")")}

if [[ ! -d "$input_root" ]]; then
  printf 'ERROR: input directory is missing: %s\n' "$input_root" >&2
  exit 1
fi

mkdir -p -- "$output_dir"

runtime_delay_seconds() {
  if [[ -n ${SYNTHETIC_SIM_RUNTIME_DELAY_SECONDS:-} ]]; then
    printf '%s\n' "$SYNTHETIC_SIM_RUNTIME_DELAY_SECONDS"
    return 0
  fi

  local min_seconds=${SYNTHETIC_SIM_RUNTIME_DELAY_MIN_SECONDS:-0}
  local max_seconds=${SYNTHETIC_SIM_RUNTIME_DELAY_MAX_SECONDS:-$min_seconds}
  python3 - "$run_id" "$min_seconds" "$max_seconds" <<'PY'
import hashlib
import sys

run_id, minimum, maximum = sys.argv[1], float(sys.argv[2]), float(sys.argv[3])
if minimum < 0 or maximum < minimum:
    raise SystemExit("invalid deterministic runtime delay range")
if maximum == minimum:
    print(f"{minimum:.6f}")
else:
    digest = hashlib.sha256(run_id.encode("utf-8")).hexdigest()
    fraction = int(digest[:12], 16) / float(0xFFFFFFFFFFFF)
    print(f"{minimum + ((maximum - minimum) * fraction):.6f}")
PY
}

delay_seconds=$(runtime_delay_seconds)
if python3 - "$delay_seconds" <<'PY'
import sys
raise SystemExit(0 if float(sys.argv[1]) > 0 else 1)
PY
then
  printf 'Applying controlled synthetic runtime delay: %s seconds\n' "$delay_seconds"
  sleep "$delay_seconds"
fi

tmp_file=$(mktemp "${output_file}.tmp.XXXXXX")
cleanup() {
  rm -f -- "$tmp_file"
}
trap cleanup EXIT

printf 'logical_group,example,bytes,sha256_prefix\n' >"$tmp_file"
for logical_group in dirA dirB dirC; do
  for example in ex1.dat ex2.dat ex3.dat; do
    input_file=$input_root/$logical_group/$example
    if [[ ! -f "$input_file" ]]; then
      printf 'ERROR: expected input file is missing: %s\n' "$input_file" >&2
      exit 1
    fi
    byte_count=$(wc -c <"$input_file" | tr -d ' ')
    sha_prefix=$(sha256sum "$input_file" | cut -d ' ' -f 1 | cut -c 1-12)
    printf '%s,%s,%s,%s\n' "$logical_group" "$example" "$byte_count" "$sha_prefix" >>"$tmp_file"
  done
done

mv -- "$tmp_file" "$output_file"
trap - EXIT
printf 'Wrote synthetic raw output: %s\n' "$output_file"
