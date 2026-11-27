#!/usr/bin/env bash
#
# Run `make sync` at the start of an agent session and print a one-line summary.
#
# Usage:
#   scripts/session-sync.sh     # called by the SessionStart hooks of .claude/settings.json
#                               # and .codex/hooks.json
#
# The agent adds what this prints to its context, so the full sync log goes to a file in this
# checkout's git directory (never versioned) and only the summary is printed. It always exits 0:
# being offline or a failing fetch must never block or fail the session.
#
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
git_dir="$(git -C "$ROOT_DIR" rev-parse --absolute-git-dir 2>/dev/null || true)"
tmp_dir="${TMPDIR:-/tmp}"
LOG="${git_dir:-${tmp_dir%/}}/session-sync.log"

# Nobody can answer a credential prompt during a hook: fail the fetch instead of hanging.
GIT_TERMINAL_PROMPT=0 make --no-print-directory -C "$ROOT_DIR" sync </dev/null >"$LOG" 2>&1
status=$?

done_line="$(grep -E '^Done: ' "$LOG" | tail -n 1)"
if [[ -z "$done_line" ]]; then
  echo "Session sync: make sync stopped before syncing (exit $status); log: $LOG"
  exit 0
fi

# "! api is on branch feat/x; fetch only" -> "api is on branch feat/x"
kept="$(sed -n 's/^! \(.*\); fetch only$/\1/p' "$LOG" | paste -sd ';' - | sed 's/;/; /g')"
failed="$(sed -n '/^Done: /,$ s/^  - //p' "$LOG" | paste -sd ',' - | sed 's/,/, /g')"

line="Session sync: ${done_line#Done: }"
[[ -n "$kept" ]] && line+=". Not moved: $kept"
[[ -n "$failed" ]] && line+=". Failed: $failed"
echo "$line. Log: $LOG"
exit 0
