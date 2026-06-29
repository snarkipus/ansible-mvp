#!/usr/bin/env bash
set -euo pipefail

# Deterministic synthetic simulation engine for the provenance MVP.
# Input contract:  <run-root>/input/{dirA,dirB,dirC}/ex{1,2,3}.dat
# Output contract: <run-root>/lists/dirC/sim-out.dat

run_root=${1:-$(pwd -P)}
input_root=$run_root/input
output_dir=$run_root/lists/dirC
output_file=$output_dir/sim-out.dat

if [[ ! -d "$input_root" ]]; then
  printf 'ERROR: input directory is missing: %s\n' "$input_root" >&2
  exit 1
fi

mkdir -p -- "$output_dir"

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
