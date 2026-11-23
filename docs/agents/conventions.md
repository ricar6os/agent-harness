# Conventions

A convention that lives only in text is followed when an agent happens to load it. Where a rule can
check it exactly, turn it into a rule, in the place where the convention lives. Where no rule can,
document it in a few lines, with the reason it is not enforced.

## Trigger

When the user corrects you on a convention, do not just apply the correction. Make it a rule in
the right place (below) before you finish.

## Where it goes

| The convention is about | It becomes | How |
| ----------------------- | ---------- | --- |
| This workspace, and should hold in every meta: the manifest, OpenSpec changes and specs, skills, MCP config, what agents may do here | A rule in the harness's `scripts/check.py` | Follow "Adding a rule" in `docs/reference/checks.md`. In the harness repository, edit `scripts/check.py` directly. In a meta, `scripts/` is harness-owned (identical in every meta): propose the rule to the harness repository, and do not fork `scripts/check.py` locally |
| This workspace, and no rule can check it exactly | A minimal doc in `docs/conventions/` of the meta (instance-owned) | Say what the convention is and why it is not enforced |
| One repository's code | A rule in that repository's own tooling (linter config, custom lint rule or test) | `create-rule`, run inside `repos/<name>` |
| One repository, and no rule can check it exactly | A minimal doc in that repository's docs | `create-rule` writes it |

## Rules in a repository

- Work in `repos/<name>` on a branch, never on its default branch. Read that repo's own
  instructions first (`AGENTS.md`, `CLAUDE.md`, its skills); its tooling decides what a rule looks like.
- Commit the rule, its tests, its baseline and its doc in their own commit. They reach the
  default branch through that repo's PR, like any other change.
- `create-rule` ends with "Add the doc to the docs index of `AGENTS.md`": that is the `AGENTS.md`
  of the repository the rule lives in, never the workspace's.
- `create-rule` ends with "push nothing and open no pull request": after it, continue with the push
  and PR steps of [working-on-a-repo.md](working-on-a-repo.md).
- `deterministify` does the same for the conventions a repository already has, written ones
  first, then the ones only the code shows. Claude Code never starts it on its own
  (`disable-model-invocation: true`); every agent starts it only when the user asks for it. It asks
  before it installs a dependency.
- If a rule would need a guess to decide, do not write it: write the minimal doc instead.

Both skills are vendored from `CodelyTV/agent-harness` (see `docs/reference/specs.md`, "Convention skills").
