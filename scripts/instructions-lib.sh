# Sourced by scripts/link-skills.sh and scripts/status.sh; not meant to be run.
#
# One definition of "a repo has instructions": it has an AGENTS.md, or a CLAUDE.md that holds
# more than an `@AGENTS.md` import (an import-only CLAUDE.md adds nothing).

# own_claude_md <repo dir>: succeeds when the repo's CLAUDE.md has content beyond the import.
own_claude_md() {
  [[ -f "$1/CLAUDE.md" ]] && grep -qvxE '[[:space:]]*(@AGENTS\.md)?[[:space:]]*' "$1/CLAUDE.md"
}

# has_instructions <repo dir>: succeeds when the repo has an AGENTS.md or an own CLAUDE.md.
has_instructions() {
  [[ -f "$1/AGENTS.md" ]] || own_claude_md "$1"
}
