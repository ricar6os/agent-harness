---
name: sync-repos
description: Clone or update the organization's repos from repos.json and report their status. Use at the start of a session, when repos/ is empty or incomplete, or when the user asks to sync or update the repos.
---

# Sync the repos

This skill drives the scripts of a meta workspace built from agent-harness (`scripts/init.sh`, `scripts/status.sh`, `repos.json`). When the workspace has none of them, say so and stop.

## 1. Sync

Run `scripts/init.sh` from the workspace root. Restrict it when the task needs only some repos:

- `--only a,b` syncs those repos, by name.
- `--product <slug>` syncs the repos of one product (`products` in `repos.json`) and the shared ones.
- `--no-update` clones what is missing and leaves existing clones as they are.

A clone that has local changes, sits on a working branch, or is detached at a commit no remote branch holds is fetched and left where it is (`! <name> ...; fetch only`). Leave it that way and report it: the user decides what to do with that work.

## 2. Report

Run `scripts/status.sh` and summarise:

- the repos with local changes (`DIRTY` is `yes`),
- the repos behind their upstream,
- the repos that failed to clone or update, with the error `init.sh` printed,
- the repos without instructions (`AGENTS` is `no`) or without a check command (`CHECK` is `no`).

## 3. Compare the manifest with the organization

Only when the user asks whether the manifest is complete. List the organization's repos with `gh repo list "$(jq -r .org repos.json)" --limit 200 --json name,isArchived` and compare them with `jq -r '.repos[].name' repos.json`. Propose the entries to add, and the archived ones to remove. Edit `repos.json` after the user confirms; removing an entry always needs their yes.
