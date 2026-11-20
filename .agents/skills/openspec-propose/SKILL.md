---
name: openspec-propose
description: Create an OpenSpec change, with its lean delta specs and its plan.md of phases, ready for review. Use when the user wants to propose, plan or specify a change, and before any work that spans several repos. Plans only.
---

# Propose a change

A proposal is planning: it writes files under `openspec/changes/<name>/` and stops. The request that started it authorizes planning only, even when it asks to build something; implementation starts when the user runs `openspec-apply-change`.

The schema of the change (`openspec/schemas/spec-plan/`) says what each artifact contains. The OpenSpec CLI hands you those rules one artifact at a time; follow what it returns instead of your memory of them.

## 1. Understand the request

- Derive a kebab-case name from it: `add-order-export`.
- Ask before creating anything when an ambiguity would change the scope, the observable behaviour or the acceptance of the change. Assume the minor details and record each assumption in the plan's Decisions.
- When `openspec/changes/<name>/` exists, ask whether to continue it or pick another name.
- Read the `context:` of `openspec/config.yaml`. It says how this workspace names repos and what a change must record (for example its product). Settle with the user whatever it asks you to resolve, and announce it.

Done when you can state the change in one sentence and the user agrees with it.

## 2. Create the change

Run `openspec new change <name>`. Add to its `.openspec.yaml` the keys the `context:` asked for.

## 3. Write the artifacts

`openspec status --change <name> --json` lists the artifacts and which are `ready`. Write them in that order: `specs`, then `plan`. For each one:

1. Run `openspec instructions <artifact> --change <name> --json`.
2. Read the files under `dependencies` again from disk: the user may have edited them.
3. Read the code, the tests and the main specs the change touches before drafting, so every requirement and every task rests on a file you opened. When the change modifies behaviour that no main spec covers, stop and ask the user to run `openspec-create-spec-from-code` first.
4. Write the file at `resolvedOutputPath`, with `template` as its structure and `instruction` as its rules. For `specs` the path is a pattern: write one `specs/<capability path>/spec.md` per capability.
5. Apply `context`, and `rules` when the CLI returns them, as constraints on what you write. Keep their text out of the file.

Done when `openspec status --change <name>` reports every artifact as done.

## 4. Validate

Run `openspec validate <name> --type change --strict`, fix every error and warning, and run it again. Then run `make check`.

Done when both pass.

## 5. Sync the tracker

Unless `x-tracker` in `openspec/config.yaml` is `none`, run `openspec-tracker-sync` for the change.

## 6. Stop and report

Report the path of the change, its capabilities, each phase with its repos, the decisions the user should check first, and any open question. Leave the files uncommitted for review, and name `/openspec-apply-change <name>` as the next step.
