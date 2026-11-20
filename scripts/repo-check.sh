#!/usr/bin/env bash
#
# Run the check command that repos.json declares for a repo, inside its clone.
#
# Usage:
#   scripts/repo-check.sh <name>   # or: make repo-check REPO=<name>
#
# The command is the manifest's "check" for that repo: the one command a contributor runs to
# verify a change (lint, types, tests). The string is run as written with `bash -c` and the exit
# status is the command's. It takes exactly one argument; for a subset of tests, run the repo's
# own command directly inside the clone. Usage errors exit 2.
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$ROOT_DIR/repos.json"

command -v jq >/dev/null 2>&1 || { echo "'jq' not found in PATH" >&2; exit 1; }
[[ -f "$MANIFEST" ]] || { echo "Manifest not found: $MANIFEST" >&2; exit 1; }

declared() {
  jq -r '.repos[] | select((.check // "") != "") | "  \(.name)\t\(.check)"' "$MANIFEST" | column -t -s $'\t'
}

usage() {
  echo "usage: scripts/repo-check.sh <name>   (or: make repo-check REPO=<name>); exactly one argument" >&2
  echo "repos that declare a check command:" >&2
  local list
  list="$(declared)"
  echo "${list:-  (none; add \"check\" to a repo in repos.json)}" >&2
}

if [[ $# -eq 0 || -z "$1" ]]; then
  echo "repo-check: no repo name given." >&2
  usage
  exit 2
fi
if [[ $# -gt 1 ]]; then
  echo "repo-check: takes exactly one argument (the repo name), got $#. To run a subset, run the repo's own command directly inside the clone." >&2
  usage
  exit 2
fi
name="$1"

entry="$(jq -c --arg n "$name" '[.repos[] | select(.name == $n)][0] // empty' "$MANIFEST")"
if [[ -z "$entry" ]]; then
  echo "repo-check: '$name' is not in repos.json. Known repos: $(jq -r '[.repos[].name] | join(", ") | if . == "" then "(none)" else . end' "$MANIFEST")" >&2
  exit 2
fi

repos_dir="$(jq -r '.root // "repos"' "$MANIFEST")"
path="$(jq -r '.path // .name' <<<"$entry")"
dir="$ROOT_DIR/$repos_dir/$path"
cmd="$(jq -r '.check // ""' <<<"$entry")"

if [[ ! -e "$dir/.git" ]]; then
  echo "repo-check: '$name' is not cloned at $repos_dir/$path. Run: make sync ONLY=$name" >&2
  exit 2
fi
if [[ -z "$cmd" ]]; then
  echo "repo-check: '$name' declares no \"check\" command in repos.json." >&2
  echo "Find it in the repo's own AGENTS.md, Makefile, package.json scripts or pyproject.toml tasks, or its CI workflow," >&2
  echo "then add it to the repo's entry in repos.json: \"check\": \"<command>\"." >&2
  exit 2
fi

echo "repo-check $name: $cmd (in $dir)" >&2
cd "$dir"
set +e
bash -c "$cmd"
exit $?
