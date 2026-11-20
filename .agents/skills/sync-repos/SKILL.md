---
name: sync-repos
description: Clone/update org repos declared in repos.json, report status. Use at session start, when repos/ empty, or user asks "update repos" / "sync".
---

# sync-repos

1. Run `scripts/init.sh` from workspace root (accepts `--only a,b` restrict by name, `--product <slug>` restrict to an OpenSpec product's repos per `products` in `repos.json`, `--no-update` leave cloned repos untouched).
2. Run `scripts/status.sh`, summarize: repos w/ local changes (`DIRTY=yes`), repos behind upstream, repos failed clone, repos without instructions or without a check command.
3. Repo w/ local changes: don't reset/stash. Report, let user decide.
4. Manifest drift from org: propose diffs comparing
   `gh repo list "$(jq -r .org repos.json)" --limit 100 --json name,isArchived` vs `jq -r '.repos[].name' repos.json`,
   don't edit `repos.json` without confirmation.