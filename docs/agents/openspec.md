# OpenSpec in this workspace

Read this before you explore, propose, apply or archive an OpenSpec change. Each rule is written in full in one place; this file says where.

## The workflow

| Step | Skill | Result |
| ---- | ----- | ------ |
| Explore (optional) | `openspec-explore` | A shared understanding in the conversation. No files. |
| Propose | `openspec-propose` | `openspec/changes/<name>/` with lean delta specs and one `plan.md` of phases. No code. |
| Apply, once per phase | `openspec-apply-change` | One phase implemented and verified, one commit per repo. Then it stops. |
| Archive | `openspec-archive-change` | Delta specs merged into `openspec/specs/`, the change moved to `openspec/changes/archive/`. |

## Where each rule is written

| Rule | Written in full in |
| ---- | ------------------ |
| What specs and `plan.md` contain; what apply does in a phase | `openspec/schemas/spec-plan/schema.yaml` and its templates. The CLI hands them to the skills. |
| How a repo named in a plan is found; products | The `context:` of `openspec/config.yaml` |
| Which tracker mirrors the phases | `x-tracker` in `openspec/config.yaml`; conventions in [issue-tracker.md](issue-tracker.md); procedure in skill `openspec-tracker-sync` |
| Branches, commits, one PR per repo and phase | [working-on-a-repo.md](working-on-a-repo.md) |

## Products and trackers

Products are optional: a change records `x-product` only when `repos.json` declares `products`, and its spec paths then start with that slug. The `change-product` rule of `make check` enforces both cases. With a tracker, each change has its own container in it, recorded in `.openspec.yaml` (`x-linear-project` or `x-github-issue`); with `x-tracker: none`, nothing is recorded. The keys this workspace adds to `.openspec.yaml` and `config.yaml` carry the `x-` prefix, which the CLI accepts without a warning.

## What this workspace uses of the OpenSpec CLI

The skills are this workspace's own, and they call the CLI for these commands only. `tests/test_openspec.py` runs each one against the schema, so an upgrade that changes them fails `make test`.

| Command | Used for |
| ------- | -------- |
| `openspec new change <name>` | Create the change with its `.openspec.yaml` |
| `openspec status --change <name> --json` | The artifacts of the schema and which are done |
| `openspec instructions <artifact\|apply> --change <name> --json` | The template and rules of an artifact, or the apply rule, with the `context:` |
| `openspec list --json`, `openspec list --specs` | Active changes with their task counts; main specs |
| `openspec validate [<name>] --strict` | The format of delta and main specs (`make check` runs `--all`) |
| `openspec archive <name> --yes` | Merge delta specs into main specs and move the change |

Run `openspec init` or `openspec update` nowhere in this workspace: they write the CLI's generic skills over these (`make check` reports it).

## Behaviour without a main spec

A change can only modify or remove a requirement that a main spec already holds. When a change is over behaviour that no main spec covers, tell the user and ask them to run `openspec-create-spec-from-code` first (only the user starts that skill).
