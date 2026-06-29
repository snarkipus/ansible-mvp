#!/usr/bin/env bash
set -euo pipefail

controlled_source_repo=${1:-../controlled-source-demo}
script_dir=$(cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
project_root=$(cd "$script_dir/.." && pwd -P)
fixture_source_dir="$project_root/templates/controlled-source-demo/fixtures/controlled_inputs"
proc_source_dir="$project_root/templates/controlled-source-demo/procs"
script_source_dir="$project_root/templates/controlled-source-demo/scripts"
expected_tag=controlled-source-demo-v0.1.0

repo_display=$controlled_source_repo
repo_parent=$(dirname -- "$controlled_source_repo")
repo_name=$(basename -- "$controlled_source_repo")

fail() {
  printf 'ERROR: %s\n' "$1" >&2
  exit 1
}

repo_physical_path() {
  local target=$1
  if [[ -d "$target" ]]; then
    (cd "$target" && pwd -P)
  else
    local parent name
    parent=$(dirname -- "$target")
    name=$(basename -- "$target")
    (cd "$parent" && printf '%s/%s\n' "$(pwd -P)" "$name")
  fi
}

if [[ -e "$controlled_source_repo" && ! -d "$controlled_source_repo" ]]; then
  fail "controlled source path exists but is not a directory: $repo_display"
fi

if [[ ! -d "$fixture_source_dir" ]]; then
  fail "controlled fixture template directory is missing: $fixture_source_dir"
fi

if [[ ! -d "$proc_source_dir" ]]; then
  fail "controlled proc template directory is missing: $proc_source_dir"
fi

if [[ ! -d "$script_source_dir" ]]; then
  fail "controlled script template directory is missing: $script_source_dir"
fi

if [[ ! -d "$controlled_source_repo" ]]; then
  mkdir -p -- "$repo_parent"
  (cd "$repo_parent" && mkdir -- "$repo_name")
  git -C "$controlled_source_repo" init
  printf 'Created controlled source Git repository at %s\n' "$repo_display"
else
  if ! git -C "$controlled_source_repo" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    fail "controlled source path exists but is not a Git worktree: $repo_display"
  fi

  repo_root=$(git -C "$controlled_source_repo" rev-parse --show-toplevel)
  repo_root=$(cd "$repo_root" && pwd -P)
  requested_root=$(repo_physical_path "$controlled_source_repo")

  if [[ "$repo_root" != "$requested_root" ]]; then
    fail "controlled source path is inside a Git worktree but is not its root: $repo_display (root: $repo_root)"
  fi

  if [[ -n $(git -C "$controlled_source_repo" status --porcelain) ]]; then
    fail "controlled source Git worktree is not clean: $repo_display"
  fi

  printf 'Verified clean controlled source Git repository at %s\n' "$repo_display"
fi

mkdir -p -- "$controlled_source_repo/fixtures"
cp -R -- "$fixture_source_dir" "$controlled_source_repo/fixtures/"

mkdir -p -- "$controlled_source_repo/procs" "$controlled_source_repo/scripts"
cp -- "$proc_source_dir/run-script.sh" "$controlled_source_repo/procs/run-script.sh"
cp -- "$script_source_dir/synthetic_sim_engine.sh" "$controlled_source_repo/scripts/synthetic_sim_engine.sh"
cp -- "$script_source_dir/extract_required.pl" "$controlled_source_repo/scripts/extract_required.pl"
cp -- "$script_source_dir/ad_hoc_extract.py" "$controlled_source_repo/scripts/ad_hoc_extract.py"
chmod 0755 \
  "$controlled_source_repo/procs/run-script.sh" \
  "$controlled_source_repo/scripts/synthetic_sim_engine.sh" \
  "$controlled_source_repo/scripts/extract_required.pl" \
  "$controlled_source_repo/scripts/ad_hoc_extract.py"

printf 'Synced controlled fixture inputs into %s/fixtures/controlled_inputs\n' "$repo_display"
printf 'Synced controlled scripts into %s/{procs,scripts}\n' "$repo_display"

git -C "$controlled_source_repo" add -- fixtures procs scripts

if ! git -C "$controlled_source_repo" rev-parse --verify HEAD >/dev/null 2>&1; then
  git -C "$controlled_source_repo" \
    -c user.name='Controlled Source Bootstrap' \
    -c user.email='controlled-source-bootstrap@example.invalid' \
    commit -m 'Bootstrap controlled source demo'
elif ! git -C "$controlled_source_repo" diff --cached --quiet; then
  git -C "$controlled_source_repo" \
    -c user.name='Controlled Source Bootstrap' \
    -c user.email='controlled-source-bootstrap@example.invalid' \
    commit -m 'Update controlled source demo'
else
  printf 'Controlled source contents already committed in %s\n' "$repo_display"
fi

resolved_commit=$(git -C "$controlled_source_repo" rev-parse HEAD)

if git -C "$controlled_source_repo" rev-parse --verify --quiet "refs/tags/$expected_tag" >/dev/null; then
  tag_commit=$(git -C "$controlled_source_repo" rev-list -n 1 "$expected_tag")
  if [[ "$tag_commit" != "$resolved_commit" ]]; then
    fail "controlled source tag $expected_tag points at $tag_commit, not current commit $resolved_commit"
  fi
  printf 'Verified controlled source tag %s at %s\n' "$expected_tag" "$resolved_commit"
else
  git -C "$controlled_source_repo" tag "$expected_tag" "$resolved_commit"
  printf 'Created controlled source tag %s at %s\n' "$expected_tag" "$resolved_commit"
fi

if [[ -n $(git -C "$controlled_source_repo" status --porcelain) ]]; then
  fail "controlled source Git worktree is not clean after bootstrap: $repo_display"
fi

printf 'Controlled source demo is committed, tagged, and clean at %s\n' "$resolved_commit"
