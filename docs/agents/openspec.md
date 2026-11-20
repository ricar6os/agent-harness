# OpenSpec in this workspace

Read this before you explore, propose, apply or archive an OpenSpec change. Each rule is written in full in one place; this file says where.

## The workflow

The workflow skills are OpenSpec's own, installed by `openspec init` (see `README.md`, "Use the schema in a repo"). This workspace changes what they produce through its schema, `spec-plan`, and its `openspec/config.yaml`.

| Step | Skill | Result with the `spec-plan` schema |
| ---- | ----- | ---------------------------------- |
| Explore (optional) | `openspec-explore` | A shared understanding in the conversation. |
| Propose | `openspec-propose` | `openspec/changes/<name>/` with lean delta specs and one `plan.md` of phases. No `proposal.md`, `design.md` or `tasks.md`. |
| Apply, once per phase | `openspec-apply-change` | The first phase with unchecked tasks, implemented and verified, with one commit per repo. Then it stops, even though the skill's own text says to continue through every task: the schema's apply rule decides. |
| Archive | `openspec-archive-change` | Delta specs merged into `openspec/specs/`, the change moved to `openspec/changes/archive/`. |

When one of those skills is missing in the session, tell the user to run `openspec init`; do not write the artifacts from memory.

## Where each rule is written

| Rule | Written in full in |
| ---- | ------------------ |
| What specs and `plan.md` contain; what apply does in a phase | `openspec/schemas/spec-plan/schema.yaml` and its templates. The CLI hands them to the skills. |
| How a repo named in a plan is found; products | The `context:` of `openspec/config.yaml` |
| When the tracker is synced | The `rules:` and `operations:` of `openspec/config.yaml` |
| Which tracker mirrors the phases, and how | `x-tracker` in `openspec/config.yaml`; conventions in [issue-tracker.md](issue-tracker.md); procedure in skill `openspec-tracker-sync` |
| Branches, commits, one PR per repo and phase | [working-on-a-repo.md](working-on-a-repo.md) |

## Products and trackers

Products are optional: a change records `x-product` only when `repos.json` declares `products`, and its spec paths then start with that slug. The `change-product` rule of `make check` enforces both cases. With a tracker, each change has its own container in it, recorded in `.openspec.yaml` (`x-linear-project` or `x-github-issue`); with `x-tracker: none`, nothing is recorded. The keys this workspace adds to `.openspec.yaml` and `config.yaml` carry the `x-` prefix, which the CLI accepts without a warning.

## Behaviour without a main spec

A change can only modify or remove a requirement that a main spec already holds. When a change is over behaviour that no main spec covers, tell the user and ask them to run `openspec-create-spec-from-code` first (only the user starts that skill). With products, its specs go under `openspec/specs/<product>/`, as the `context:` says.
