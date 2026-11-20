# OpenSpec: where each rule is written

Read this before you propose, apply or archive an OpenSpec change. Each rule is written in full
in one place; follow the pointer instead of copying it.

## The workflow

`/openspec-explore` (optional) → `/openspec-propose` → `/openspec-apply-change`, once per phase →
`/openspec-archive-change`. The schema `spec-plan` (`openspec/schemas/spec-plan/`) defines the
two artifacts of a change, lean delta specs and one `plan.md` of vertical slice phases, and the
apply behaviour: one phase per run, verified, one commit per repo, then stop.

| Rule | Written in full in |
| ---- | ------------------ |
| What specs and `plan.md` contain, phases, `**Repos:**` lines, contracts, tests, apply | `openspec/schemas/spec-plan/schema.yaml` and its templates |
| How a repo named in a plan is found, products, Linear hooks | `openspec/config.yaml`, which the CLI injects into every operation |
| Linear conventions | [issue-tracker.md](issue-tracker.md) |
| Sync procedure and the one status the agent writes | skill `openspec-linear-sync` |
| Branches, PR titles, one PR per repo and phase | [working-on-a-repo.md](working-on-a-repo.md) |

## Products and Linear projects

Products are optional: a change records `x-product` only when `repos.json` declares `products`,
and its spec paths then start with that slug. The `change-product` rule of `make check`
enforces both cases. Each change has its own Linear project, recorded as `x-linear-project`.
The keys of `.openspec.yaml` carry the `x-` prefix because OpenSpec 2 keeps only those without
a warning.

## Repos in a plan

The schema never says where a repo lives: it names repos and defers to the workspace. This
workspace resolves a name through `repos.json` (`repos/<name>`, verified with
`make repo-check REPO=<name>`). A single-repo workspace or an OpenSpec store resolves it its own
way in `openspec/config.yaml`, and the schema stays the same.

## Behaviour without a main spec

When a change is over behaviour that has no main spec, tell the user that no main spec covers it
and ask them to run `openspec-create-spec-from-code` first (the skill is user-invoked only), so
the change can modify or remove requirements instead of only adding.
