#!/usr/bin/env bash
#
# Expose the skills and instructions of every cloned repo to agents launched from the meta root.
#
# Usage:
#   scripts/link-skills.sh          # also called by scripts/init.sh after every sync
#
# Claude Code loads skills below the start directory only once it touches a file there (and in
# practice never from the git-ignored repos/), and Codex only reads .agents/skills/ from the working directory upwards, so neither offers
# repos/<name> skills while working from here. For each skill directory in
# repos/<name>/.agents/skills/ (or .claude/skills/ when the repo has no .agents/ copy), this
# creates the symlink <repo>--<skill> in .claude/skills/ and .agents/skills/. The repo stays
# the only copy.
#
# Neither tool reliably applies a repo's AGENTS.md from here either: Codex never loads it, and
# Claude Code attaches it to a tool result, which models may discard as injected text. Skills
# are the one channel every harness lists up front, so for each repo with an AGENTS.md or
# CLAUDE.md, or a "check" command in the manifest, this also generates the skill
# <repo>--instructions, which points at those files, says when there are none, and names
# `make repo-check REPO=<name>` as the way to verify changes.
#
# A linked git worktree that has not cloned a repo itself links to the main checkout's clone,
# so a fresh worktree offers every repo skill without a full sync.
#
# Both tools name a skill after its SKILL.md frontmatter, not the link, so only one copy of
# each skill name is linked: a skill meta already has is skipped, and when several repos ship
# the same skill the copy with the most recent commit wins (uncommitted copies count as
# newest). A skill that at least two repos install from the same source in skills-lock.json is
# linked as shared--<skill> instead, since it belongs to none of them. Links and generated
# skills are git-ignored and rebuilt from scratch on every run.
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$ROOT_DIR/repos.json"
REPOS_DIR="$(jq -r '.root // "repos"' "$MANIFEST")"
TARGETS=(.claude/skills .agents/skills)
GENERATED_MARK=.generated-by-link-skills
# shellcheck source=instructions-lib.sh
source "$ROOT_DIR/scripts/instructions-lib.sh"

# Clones of this checkout first, then the main checkout's when this is a linked worktree.
# --git-common-dir is the main checkout's .git even from a linked worktree.
REPO_ROOTS=("$ROOT_DIR/$REPOS_DIR")
common_dir="$(git -C "$ROOT_DIR" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
main_root="${common_dir:+$(dirname "$common_dir")}"
[[ -n "$main_root" && "$main_root" != "$ROOT_DIR" ]] && REPO_ROOTS+=("$main_root/$REPOS_DIR")

for target in "${TARGETS[@]}"; do
  mkdir -p "$ROOT_DIR/$target"
  for link in "$ROOT_DIR/$target"/*--*; do
    if [[ -L "$link" ]]; then
      rm "$link"
    elif [[ -f "$link/$GENERATED_MARK" ]]; then
      rm -r "$link"
    fi
  done
done

# rel_or_abs <path>: the path relative to the meta root when inside it, else absolute.
rel_or_abs() {
  if [[ "$1" == "$ROOT_DIR"/* ]]; then echo "${1#"$ROOT_DIR"/}"; else echo "$1"; fi
}

# One line per repo: name, path. A repo of this checkout hides the main checkout's clone.
repos() {
  local repos_root repo_path repo seen=$'\n'
  for repos_root in "${REPO_ROOTS[@]}"; do
    for repo_path in "$repos_root"/*/; do
      [[ -d "$repo_path" ]] || continue
      repo_path="${repo_path%/}"
      repo="$(basename "$repo_path")"
      [[ "$seen" == *$'\n'"$repo"$'\n'* ]] && continue
      seen+="$repo"$'\n'
      printf '%s\t%s\n' "$repo" "$repo_path"
    done
  done
}

# One line per candidate: skill, commit time, repo, link target, skills-lock.json source ("-"
# when the repo does not lock it; read collapses empty tab-separated fields).
candidates() {
  local repo repo_path skill_path skill rel ts dest source seen
  while IFS=$'\t' read -r repo repo_path; do
    seen=$'\n'
    # Repos keep .claude/skills/ as symlinks into .agents/skills/: take each name once.
    for skill_path in "$repo_path"/.agents/skills/*/ "$repo_path"/.claude/skills/*/; do
      skill_path="${skill_path%/}"
      [[ -f "$skill_path/SKILL.md" ]] || continue
      skill="$(basename "$skill_path")"
      [[ "$seen" == *$'\n'"$skill"$'\n'* ]] && continue
      seen+="$skill"$'\n'
      rel="${skill_path#"$repo_path"/}"
      ts="$(git -C "$repo_path" log -1 --format=%ct -- "$rel" 2>/dev/null || true)"
      if [[ -z "$ts" || -n "$(git -C "$repo_path" status --porcelain -- "$rel" 2>/dev/null)" ]]; then
        ts="$(date +%s)"
      fi
      dest="$(rel_or_abs "$skill_path")"
      [[ "$dest" == /* ]] || dest="../../$dest"
      source="-"
      if [[ -f "$repo_path/skills-lock.json" ]]; then
        source="$(jq -r --arg s "$skill" '.skills[$s].source // "-"' "$repo_path/skills-lock.json" 2>/dev/null || echo -)"
      fi
      printf '%s\t%s\t%s\t%s\t%s\n' "$skill" "$ts" "$repo" "$dest" "$source"
    done
  done < <(repos)
}

# mark_shared: append 1 to every candidate of a skill whose newest copy shares its lock
# source with at least one other repo's copy, else 0. Input is sorted, newest copy first.
mark_shared() {
  awk -F'\t' -v OFS='\t' '
    { line[NR] = $0; skill[NR] = $1; source[NR] = $5 }
    END {
      for (i = 1; i <= NR; i++) {
        if (skill[i] != skill[i - 1]) {
          n = 0
          for (j = i; j <= NR && skill[j] == skill[i]; j++)
            if (source[i] != "-" && source[j] == source[i]) n++
        }
        print line[i], (n >= 2 ? 1 : 0)
      }
    }'
}

linked=0; skipped=0; winner=""; winner_source=""; prev=""
while IFS=$'\t' read -r skill ts repo dest source shared; do
  if [[ "$skill" == "$prev" ]]; then
    if [[ "$shared" == 1 && "$source" == "$winner_source" ]]; then
      echo "  = $repo--$skill skipped (same $source skill as $winner)"
    else
      echo "  = $repo--$skill skipped ($winner has a newer copy)"
    fi
    skipped=$((skipped+1)); continue
  fi
  name="$repo--$skill"
  [[ "$shared" == 1 ]] && name="shared--$skill"
  prev="$skill"; winner="$name"; winner_source="$source"
  if [[ -e "$ROOT_DIR/.agents/skills/$skill" || -e "$ROOT_DIR/.claude/skills/$skill" ]]; then
    echo "  = $name skipped (meta has its own $skill)"
    winner="meta's $skill"; winner_source=""; skipped=$((skipped+1)); continue
  fi
  for target in "${TARGETS[@]}"; do
    ln -sfn "$dest" "$ROOT_DIR/$target/$name"
  done
  linked=$((linked+1))
done < <(candidates | sort -t $'\t' -k1,1 -k2,2nr -k3,3 | mark_shared)

# manifest_entry <dir name>: "1<TAB>name<TAB>check" for the manifest repo whose clone directory
# (its "path", else its "name") is <dir name>; "0" when the manifest does not list it.
manifest_entry() {
  jq -r --arg d "$1" '
    [.repos[] | select(((.path // .name) | sub("^\\./"; "") | sub("/$"; "")) == $d)][0]
    | if . == null then "0" else "1\t\(.name)\t\(.check // "")" end' "$MANIFEST"
}

# write_instructions <dir name> <dir> <files> <manifest name> <check> <local>: generate the
# <dir name>--instructions skill. <files> is empty when the repo has no instructions file;
# <check> is empty when the manifest declares no check command; <local> is 0 when the clone
# belongs to the main checkout, so this checkout cannot run the check before a sync.
write_instructions() {
  local repo="$1" dir="$2" files="$3" name="$4" check="$5" is_local="$6" skill="$1--instructions"
  mkdir -p "$ROOT_DIR/.agents/skills/$skill"
  : > "$ROOT_DIR/.agents/skills/$skill/$GENERATED_MARK"
  {
    echo "---"
    echo "name: $skill"
    echo "description: Mandatory rules of the $repo repository. Use before reading, editing, reviewing, testing or committing anything under $dir/."
    echo "---"
    echo "<!-- Generated by scripts/link-skills.sh; do not edit. -->"
    echo
    if [[ -n "$files" ]]; then
      echo "Before working under \`$dir/\`, read $files and follow those rules. They override"
      echo "the workspace's \`AGENTS.md\` and \`docs/agents/\` for that repository."
    else
      echo "\`$dir/\` has no \`AGENTS.md\`: follow the conventions of the code being edited, and propose"
      echo "adding an \`AGENTS.md\` to that repo when a convention has to be explained twice."
    fi
    if [[ -n "$check" ]]; then
      echo
      if [[ "$is_local" == 1 ]]; then
        echo "Verify changes with \`make repo-check REPO=$name\` (it runs \`$check\` in \`$dir/\`) before"
        echo "committing."
      else
        echo "\`$name\` is not cloned in this checkout (these files are read from the main checkout). Run"
        echo "\`make sync ONLY=$name\` first, then \`make repo-check REPO=$name\` (it runs \`$check\`) to verify"
        echo "changes before committing."
      fi
    fi
  } > "$ROOT_DIR/.agents/skills/$skill/SKILL.md"
  ln -sfn "../../.agents/skills/$skill" "$ROOT_DIR/.claude/skills/$skill"
}

# A CLAUDE.md that only imports AGENTS.md adds nothing, so it is not listed. A repo of the
# manifest also gets the skill when it only declares a check command; a clone that is not in
# the manifest needs instructions files.
instructions=0
while IFS=$'\t' read -r repo repo_path; do
  dir="$(rel_or_abs "$repo_path")"
  files=""
  [[ -f "$repo_path/AGENTS.md" ]] && files="\`$dir/AGENTS.md\`"
  if own_claude_md "$repo_path"; then
    files+="${files:+ and }\`$dir/CLAUDE.md\`"
  fi
  in_manifest=0; name="$repo"; check=""
  IFS=$'\t' read -r in_manifest m_name check <<<"$(manifest_entry "$repo")" || true
  [[ "$in_manifest" == 1 ]] && name="$m_name" || check=""
  [[ -n "$files" || -n "$check" ]] || continue
  is_local=0
  [[ "$repo_path" == "$ROOT_DIR"/* ]] && is_local=1
  write_instructions "$repo" "$dir" "$files" "$name" "$check" "$is_local"
  instructions=$((instructions+1))
done < <(repos)

echo "Skills: $linked linked from $REPOS_DIR/, $skipped skipped, $instructions instruction skills generated"
