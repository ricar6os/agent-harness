#!/usr/bin/env bash
#
# Regenerate the openspec-* skills (and the .claude/skills links to them) with the pinned CLI
# version and profile.
#
# Usage: scripts/openspec-update.sh [target-dir]    (default: the repository root)
#
# The CLI version is pinned in <target>/openspec/cli-version; the script refuses to run with any
# other version. The OpenSpec CLI reads its profile from a per-user config file and writes
# telemetry keys into it, so the tracked openspec/cli-profile.json is never used in place: it is
# copied into a throwaway XDG_CONFIG_HOME for each run, which keeps the result independent of the
# developer's own CLI configuration and leaves the tracked file untouched. stdin is /dev/null so
# the CLI can never stop to ask a question.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target="${1:-$root}"
target="$(cd "$target" && pwd)"
profile="$target/openspec/cli-profile.json"
pin_file="$target/openspec/cli-version"

[[ -f "$profile" ]] || { echo "error: $profile not found; it pins the OpenSpec CLI profile." >&2; exit 1; }
[[ -f "$pin_file" ]] || { echo "error: $pin_file not found; it pins the OpenSpec CLI version (for example: 2.1.1)." >&2; exit 1; }
pin="$(tr -d '[:space:]' < "$pin_file")"
command -v openspec >/dev/null 2>&1 || {
  echo "error: the openspec CLI is not installed. Install it with: npm i -g @fission-ai/openspec@$pin" >&2
  exit 1
}
installed="$(openspec --version 2>/dev/null | tr -d '[:space:]')"
[[ "$installed" == "$pin" ]] || {
  echo "error: openspec $pin is pinned in $pin_file, found ${installed:-none}. Install it with: npm i -g @fission-ai/openspec@$pin" >&2
  exit 1
}

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/openspec"
cp "$profile" "$tmp/openspec/config.json"

cd "$target"
XDG_CONFIG_HOME="$tmp" DO_NOT_TRACK=1 openspec update --force < /dev/null
