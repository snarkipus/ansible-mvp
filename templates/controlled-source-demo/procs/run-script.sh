#!/usr/bin/env bash
set -euo pipefail

# Runtime entrypoint copied into sim-run-root/procs/run-script.sh.
# It delegates to the tracked controlled source simulation engine while keeping
# the simulation working directory as the output root.

script_dir=$(cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)

if [[ $# -gt 0 ]]; then
  run_root=$1
elif [[ $(basename -- "$script_dir") == "procs" && -d "$script_dir/../input" ]]; then
  run_root=$(cd "$script_dir/.." && pwd -P)
else
  run_root=$(pwd -P)
fi

engine_path=${SYNTHETIC_SIM_ENGINE:-}
if [[ -z "$engine_path" && -n ${CONTROLLED_SOURCE_REPO:-} ]]; then
  engine_path=$CONTROLLED_SOURCE_REPO/scripts/synthetic_sim_engine.sh
fi
if [[ -z "$engine_path" && -x "$script_dir/../scripts/synthetic_sim_engine.sh" ]]; then
  engine_path=$script_dir/../scripts/synthetic_sim_engine.sh
fi

if [[ -z "$engine_path" || ! -x "$engine_path" ]]; then
  printf 'ERROR: synthetic simulation engine is not executable or was not found. Set CONTROLLED_SOURCE_REPO or SYNTHETIC_SIM_ENGINE.\n' >&2
  exit 1
fi

exec "$engine_path" "$run_root"
