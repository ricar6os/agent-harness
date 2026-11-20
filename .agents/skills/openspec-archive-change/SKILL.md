---
name: openspec-archive-change
description: Archive a finished OpenSpec change, merging its delta specs into the main specs. Use when every phase of a change is implemented and merged, or the user asks to archive or close a change.
---

# Archive a change

Archiving merges the delta specs of a change into `openspec/specs/` and moves the change to `openspec/changes/archive/`. The OpenSpec CLI does both; this skill decides whether the change is ready and checks the result.

## 1. Select the change

Use the change the user named. Otherwise run `openspec list --json`: with exactly one active change, use it and say so; with several, ask which one.

## 2. Check that it is finished

- **Tasks.** In `openspec list --json`, the change's `completedTasks` must equal its `totalTasks`. When tasks remain, list the phases of `plan.md` that hold them.
- **Tracker.** Unless `x-tracker` in `openspec/config.yaml` is `none`, run `openspec-tracker-sync` and list the phases whose issue is not finished.
- **Format.** Run `openspec validate <name> --type change --strict` and fix every error and warning.

When tasks or issues remain, show them and ask whether to archive anyway. Go on only with the user's yes.

## 3. Archive

Run `openspec archive <name> --yes`. When it fails, show its message and stop: the change stays where it was. A delta that the CLI cannot merge (for example a `MODIFIED` requirement that the main spec lacks) is fixed in the delta spec, with the user, and then archived again. Leave the merge to the CLI: a main spec edited by hand loses the record of what the change did.

## 4. Verify and report

Run `openspec validate --all --strict` and `make check`. When a merged main spec fails on format (a Purpose under 50 characters, a scenario keyword), fix the format in the main spec and keep its behaviour as merged.

Report the main specs created and updated, with the counts the CLI printed, and the archive path. Leave the result uncommitted, and name the next step: commit it on a branch of the repo that holds `openspec/` (`docs(openspec): archive <name>`) and open its pull request with `create-pull-request`.
