#!/usr/bin/env bash
# Print branch, local changes and ahead/behind for every cloned repo.
# A detached HEAD (repos added as worktrees start that way) shows as detached@<sha> and is
# compared with the remote default branch instead of an upstream. AGENTS says whether the clone
# has instructions (an AGENTS.md, or a CLAUDE.md beyond an @AGENTS.md import), CHECK whether repos.json declares a check command for it.
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=instructions-lib.sh
source "$ROOT_DIR/scripts/instructions-lib.sh"
REPOS_ROOT="$ROOT_DIR/$(jq -r '.root // "repos"' "$ROOT_DIR/repos.json")"

printf '%-20s %-36s %-8s %-7s %-6s %s\n' REPO BRANCH DIRTY AGENTS CHECK AHEAD/BEHIND
no_instructions=0; no_check=0
for d in "$REPOS_ROOT"/*/; do
  [[ -e "$d/.git" ]] || continue
  name="$(basename "$d")"
  branch="$(git -C "$d" rev-parse --abbrev-ref HEAD 2>/dev/null || echo '?')"
  base="@{upstream}"
  if [[ "$branch" == HEAD ]]; then
    branch="detached@$(git -C "$d" rev-parse --short HEAD)"
    base="$(git -C "$d" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null || echo origin/main)"
  fi
  dirty="$([[ -n "$(git -C "$d" status --porcelain)" ]] && echo yes || echo no)"
  ab="$(git -C "$d" rev-list --left-right --count "$base...HEAD" 2>/dev/null | awk '{print $2"/"$1}' || true)"
  [[ "$base" != "@{upstream}" && -n "$ab" ]] && ab="$ab vs $base"
  agents=no
  if has_instructions "$d"; then agents=yes; else no_instructions=$((no_instructions+1)); fi
  has_check="$(jq -r --arg d "$name" '
    [.repos[] | select(((.path // .name) | sub("^\\./"; "") | sub("/$"; "")) == $d and ((.check // "") != ""))] | length' "$ROOT_DIR/repos.json")"
  check=no
  if [[ "$has_check" -gt 0 ]]; then check=yes; else no_check=$((no_check+1)); fi
  printf '%-20s %-36s %-8s %-7s %-6s %s\n' "$name" "$branch" "$dirty" "$agents" "$check" "${ab:--}"
done
if [[ $no_instructions -gt 0 || $no_check -gt 0 ]]; then
  echo
  echo "$no_instructions repo(s) without instructions, $no_check without a check command"
fi
