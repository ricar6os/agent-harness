---
name: openspec-apply-change
description: Implement the next phase of an OpenSpec change, verify it, commit it and stop. Use when the user wants to apply, implement or continue a change. One phase per run.
---

# Apply one phase of a change

Each run implements one phase: the first phase of `plan.md` with unchecked tasks. The user reviews it and runs this skill again for the next one.

## 1. Select the change

Use the change the user named. Otherwise run `openspec list --json`: with exactly one active change, use it and say so; with several, ask which one.

## 2. Load the phase

Run `openspec instructions apply --change <name> --json` and read its `state`:

- `blocked`: show its message and stop. A missing artifact means the change needs `openspec-propose` first.
- `all_done`: say that every phase is implemented, name `/openspec-archive-change <name>` as the next step, and stop.
- otherwise: go on.

Read every file under `contextFiles`. Announce the change, the phase you will implement and its repos.

## 3. Mark the phase started

Unless `x-tracker` in `openspec/config.yaml` is `none`: when the phase heading ends in an issue reference and none of its tasks is checked yet, mark that issue started as the "State" section of `openspec-tracker-sync` says.

## 4. Implement the phase

Follow the `instruction` the CLI returned, step by step: it is the apply rule of the schema, and it ends with one commit per repo. Apply `context` while you do: it says how this workspace finds each repo and its verification command.

- Check off a task only when its behaviour is fully implemented and verified.
- Stop and ask when a task is unclear, when a check keeps failing, or when the code contradicts the plan or the specs. A contradiction is fixed in `plan.md` or the delta specs first, with the user's agreement, and then in the code.
- Work beyond what the phase describes is new scope: name it and ask.

Done when every task of the phase is checked, every repo it touched passes its verification command, and each of those repos has its commit.

## 5. Stop and report

Report, per repo: the branch, the commit and the result of its verification command. Then the phases that remain. Name the next steps: review the phase, open its pull requests with `create-pull-request` (one per repo, in the order of the phase's `**Repos:**` line), and run `/openspec-apply-change <name>` again for the next phase.
