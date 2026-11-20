# OpenSpec: where each rule is written

Read this before you propose, update, sync or apply an OpenSpec change. Each rule is written in
full in one place; follow the pointer instead of copying it.

## Products and Linear projects

| Rule | Written in full in |
| ---- | ------------------ |
| Product and Linear project of a change, spec paths, task groups, `Depends on:` lines, `## Contracts` and `## Deployment order` of a multi-repo change | `openspec/config.yaml` (`context:` and `rules:`), which the OpenSpec CLI injects into every operation; the one Linear status the agent writes is in `operations.apply.guidance` of the same file |
| Linear conventions: tool, issue ids, reading before writing, what never changes | [issue-tracker.md](issue-tracker.md) |
| Sync procedure, labels, mapping, state, legacy migration | skill `openspec-linear-sync` |
| PR title and one PR per repo | [working-on-a-repo.md](working-on-a-repo.md) |

The keys of a change's `.openspec.yaml` are `x-product`, `x-linear-project` and
`x-linear-sync-version` (OpenSpec 2 keeps only `x-` keys without a warning).

## Behaviour without a main spec

When a change is over behaviour that has no main spec, tell the user that no main spec covers it
and ask them to run `openspec-create-spec-from-code` first (the skill is user-invoked only), so
the change can modify or remove requirements instead of only adding.
