#!/usr/bin/env bash
#
# Clone (or update) the repositories declared in repos.json into ./repos/.
#
# Usage:
#   scripts/init.sh                 # clone missing repos and update existing ones
#   scripts/init.sh --no-update     # only clone missing repos
#   scripts/init.sh --only a,b,c    # restrict to those repos (by name)
#   scripts/init.sh --product shop # restrict to the repos of a product (slug in "products";
#                                   # a repo without "products" belongs to every product)
#   scripts/init.sh --list          # print the manifest and exit
#
# After cloning or updating, every file under env/<name>/ (except .gitkeep) is symlinked
# into repos/<name>/. Files are taken from env/ of the main checkout (shared by every git
# worktree) and then from env/ of this checkout, which wins (see env/README.md).
#
# In a linked git worktree of meta, a missing repo that the main checkout has cloned is added
# as a git worktree of that clone, detached at origin/<branch>, instead of cloned again: it is
# fast, shares objects, and gives each meta worktree its own checkout. Create a branch in it
# before committing.
#
# Updating an existing repo fetches it, then moves it only when that loses no work: a clean repo
# on <branch> is fast-forwarded, and a clean detached one goes back to <branch> (to origin/<branch>,
# still detached, in a worktree) when a remote branch holds its commit. A repo with local
# changes, on any other branch, or detached at a commit no remote branch has is fetched only.
#
# Finally scripts/link-skills.sh exposes the skills and instructions of every cloned repo to
# agents launched from the meta root.
#
# Environment:
#   CLONE_DEPTH=1                   # shallow clone (default: full history)
#   META_ENV_DIR=/path              # use only this env/ directory instead of the two above
#   META_REPO_WORKTREES=0           # in a meta worktree, clone repos instead of adding worktrees
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$ROOT_DIR/repos.json"

UPDATE=1
ONLY=""
SYNC_PRODUCT=""
LIST=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-update) UPDATE=0 ;;
    --only) ONLY="$2"; shift ;;
    --only=*) ONLY="${1#--only=}" ;;
    --product) SYNC_PRODUCT="$2"; shift ;;
    --product=*) SYNC_PRODUCT="${1#--product=}" ;;
    --list) LIST=1 ;;
    -h|--help) sed -n '2,34p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

for bin in git jq; do
  command -v "$bin" >/dev/null 2>&1 || { echo "'$bin' not found in PATH" >&2; exit 1; }
done
[[ -f "$MANIFEST" ]] || { echo "Manifest not found: $MANIFEST" >&2; exit 1; }

REPOS_ROOT="$ROOT_DIR/$(jq -r '.root // "repos"' "$MANIFEST")"
mkdir -p "$REPOS_ROOT"

# Local env files come from two places, in this order (later wins): env/ of the main
# checkout, shared by every linked git worktree, and env/ of this checkout. META_ENV_DIR
# replaces both. --git-common-dir is the main checkout's .git even from a linked worktree.
common_dir="$(git -C "$ROOT_DIR" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
main_root="${common_dir:+$(dirname "$common_dir")}"
[[ "$main_root" == "$ROOT_DIR" ]] && main_root=""
ENV_DIRS=()
if [[ -n "${META_ENV_DIR:-}" ]]; then
  ENV_DIRS=("$META_ENV_DIR")
else
  [[ -n "$main_root" ]] && ENV_DIRS+=("$main_root/env")
  ENV_DIRS+=("$ROOT_DIR/env")
fi

# Clones of the main checkout that a linked worktree adds repos from (see the header).
MAIN_REPOS_ROOT=""
if [[ -n "$main_root" && "${META_REPO_WORKTREES:-1}" != 0 ]]; then
  MAIN_REPOS_ROOT="$main_root/$(jq -r '.root // "repos"' "$MANIFEST")"
fi

# link_env <name> <dest>: symlink <env dir>/<name>/* into the cloned repo. Existing symlinks
# are refreshed; a regular file is left alone with a warning so local edits are never lost.
link_env() {
  local name="$1" dest="$2" env_dir src_dir src target base
  for env_dir in "${ENV_DIRS[@]}"; do
    src_dir="$env_dir/$name"
    [[ -d "$src_dir" ]] || continue
    for src in "$src_dir"/.[!.]* "$src_dir"/*; do
      [[ -f "$src" ]] || continue
      base="$(basename "$src")"
      case "$base" in .gitkeep|README.md) continue ;; esac
      target="$dest/$base"
      if [[ -e "$target" && ! -L "$target" ]]; then
        echo "  ! $name/$base exists in the repo and is not a symlink; left untouched"
        continue
      fi
      ln -sfn "$src" "$target"
      echo "  -> $name/$base linked from $env_dir"
    done
  done
}

if [[ $LIST -eq 1 ]]; then
  jq -r '.repos[] | "\(.name)\t\(.branch // "main")\t\((.products // ["*"]) | join(","))\t\(.url)\t\(.check // "-")"' "$MANIFEST" | column -t -s $'\t'
  exit 0
fi

if [[ -n "$ONLY" ]]; then
  for wanted in ${ONLY//,/ }; do
    jq -e --arg n "$wanted" '.repos[] | select(.name == $n)' "$MANIFEST" >/dev/null \
      || echo "warning: '$wanted' is not in $MANIFEST (ignored)" >&2
  done
fi

if [[ -n "$SYNC_PRODUCT" ]]; then
  jq -e --arg p "$SYNC_PRODUCT" '.repos[] | select(.products // [] | index($p))' "$MANIFEST" >/dev/null \
    || echo "warning: no repo in $MANIFEST lists product '$SYNC_PRODUCT'; only shared repos (no \"products\") match" >&2
fi

ok=0; skipped=0; failed=0
failed_names=()

while IFS=$'\t' read -r name url branch path products; do
  if [[ -n "$ONLY" ]] && ! grep -qx "$name" <<<"${ONLY//,/$'\n'}"; then
    continue
  fi
  # A repo without "products" (listed as "*") is shared by every product.
  if [[ -n "$SYNC_PRODUCT" && "$products" != "*" ]] && ! grep -qx "$SYNC_PRODUCT" <<<"${products//,/$'\n'}"; then
    continue
  fi

  [[ "$branch" == "null" || -z "$branch" ]] && branch="main"
  dest="$REPOS_ROOT/$path"

  main_clone="${MAIN_REPOS_ROOT:+$MAIN_REPOS_ROOT/$path}"

  # A git worktree has a .git file instead of a directory.
  if [[ -e "$dest/.git" ]]; then
    if [[ $UPDATE -eq 0 ]]; then
      echo "= $name (already present, not updated)"; link_env "$name" "$dest"; skipped=$((skipped+1)); continue
    fi
    # Only a clean clone on the default branch, or detached at a commit some remote branch
    # holds, is moved. Anything else may hold work in progress: fetch only, never move it.
    keep=""
    current="$(git -C "$dest" symbolic-ref --quiet --short HEAD || true)"
    if [[ -n "$(git -C "$dest" status --porcelain)" ]]; then
      keep="has local changes"
    elif [[ -n "$current" && "$current" != "$branch" ]]; then
      keep="is on branch $current"
    fi
    if ! git -C "$dest" fetch --quiet --all --prune; then
      echo "  failed to fetch $name" >&2; failed=$((failed+1)); failed_names+=("$name"); continue
    fi
    # A commit made while detached is on no branch: moving HEAD would leave it dangling.
    if [[ -z "$keep" && -z "$current" ]] \
       && [[ -z "$(git -C "$dest" for-each-ref --count=1 --contains HEAD refs/remotes/)" ]]; then
      keep="is detached at a commit no remote branch has"
    fi
    if [[ -n "$keep" ]]; then
      echo "! $name $keep; fetch only"
      link_env "$name" "$dest"
      skipped=$((skipped+1)); continue
    fi
    if [[ -z "$current" && -f "$dest/.git" ]]; then
      # The branch may be checked out in another worktree, so follow origin detached.
      echo "~ $name (moving worktree to origin/$branch)"
      if git -C "$dest" checkout --quiet --detach "origin/$branch"; then
        link_env "$name" "$dest"
        ok=$((ok+1))
      else
        echo "  failed to update $name" >&2; failed=$((failed+1)); failed_names+=("$name")
      fi
      continue
    fi
    echo "~ $name (updating $branch)"
    if { [[ "$current" == "$branch" ]] || git -C "$dest" checkout --quiet "$branch"; } \
       && git -C "$dest" merge --quiet --ff-only "origin/$branch"; then
      link_env "$name" "$dest"
      ok=$((ok+1))
    else
      echo "  failed to update $name" >&2; failed=$((failed+1)); failed_names+=("$name")
    fi
  elif [[ -n "$main_clone" && -d "$main_clone/.git" ]]; then
    echo "+ $name (worktree of the main checkout's clone at origin/$branch -> $path)"
    if git -C "$main_clone" fetch --quiet origin "$branch" \
       && git -C "$main_clone" worktree prune \
       && git -C "$main_clone" worktree add --quiet --detach "$dest" "origin/$branch"; then
      link_env "$name" "$dest"
      ok=$((ok+1))
    else
      echo "  failed to add a worktree for $name" >&2; failed=$((failed+1)); failed_names+=("$name")
    fi
  else
    echo "+ $name (cloning $branch -> $path)"
    depth_args=()
    [[ -n "${CLONE_DEPTH:-}" ]] && depth_args=(--depth "$CLONE_DEPTH")
    if git clone --quiet ${depth_args[@]+"${depth_args[@]}"} --branch "$branch" "$url" "$dest"; then
      link_env "$name" "$dest"
      ok=$((ok+1))
    else
      echo "  failed to clone $name" >&2; failed=$((failed+1)); failed_names+=("$name")
    fi
  fi
# Every field is non-empty: `read` with a tab IFS collapses consecutive tabs, so an empty
# field in the middle would shift the columns after it.
done < <(jq -r '.repos[] | [.name, .url, (.branch // "main"), (.path // .name), ((.products // ["*"]) | join(","))] | @tsv' "$MANIFEST")

echo
"$ROOT_DIR/scripts/link-skills.sh" || echo "  failed to link repo skills" >&2
echo "Done: $ok ok, $skipped unchanged, $failed failed"
if [[ $failed -gt 0 ]]; then
  printf '  - %s\n' ${failed_names[@]+"${failed_names[@]}"}
  exit 1
fi
