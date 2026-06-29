#!/usr/bin/env bash
set -euo pipefail

controlled_source_repo=${1:-../controlled-source-demo}
script_dir=$(cd "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
project_root=$(cd "$script_dir/.." && pwd -P)
fixture_source_dir="$project_root/templates/controlled-source-demo/fixtures/controlled_inputs"

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

printf 'Synced controlled fixture inputs into %s/fixtures/controlled_inputs\n' "$repo_display"
printf 'Fixture files are ready for the controlled source commit/tag step owned by ansible-mvp-izo.2.4.\n'
