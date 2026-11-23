# Specs reference

How changes are specified, planned and tracked with OpenSpec and the `spec-plan` schema.

## Three layers

The harness keeps apart what every workspace needs, where the code lives and how work is
planned, so each part can change without the others:

| Layer | What | Files |
| ----- | ---- | ----- |
| Core | Agent instructions as a map, guardrails, checks, MCP parity, secrets, PR and rule skills | `AGENTS.md`, `docs/agents/`, `scripts/`, `.agents/skills/` |
| Topology | Where the code lives: one repo, this meta with `repos.json`, or an OpenSpec store (beta, not wired yet) | `repos.json`, `scripts/init.sh`, the `context:` of `openspec/config.yaml` |
| Method | How a change is specified, planned and implemented | `openspec/schemas/spec-plan/`, driven by OpenSpec's own workflow skills |

The method touches the topology in one place: a plan names repos, and the workspace says how a
name becomes a checkout and a verification command. Here that is `repos.json` and
`make repo-check REPO=<name>`, written in the `context:` of `openspec/config.yaml`. The schema
stays the same in a single repo, in this meta, or in a store.

## Specs (OpenSpec)

Changes use our own schema, `spec-plan` (`openspec/schemas/spec-plan/`), adapted from
[CodelyTV/agent-harness](https://github.com/CodelyTV/agent-harness)'s `codely-spec-plan`. A change has
two artifacts:

- **Lean delta specs**: one behaviour per requirement, one-line scenarios.
- **One `plan.md`**: goal, decisions and phases. Each phase is a vertical slice worth having on
  its own, with its `**Repos:**` in deployment order, its contracts (naming the repo that provides
  each one that crosses repos), its test strategy and its tasks.

There is no `proposal.md`, `design.md` or `tasks.md`. Apply implements only the first phase with
unchecked tasks: it works on a branch in each repo of the phase, runs each repo's check, commits
once per repo and stops. It never pushes or opens a PR; that is `create-pull-request`, after you
review the phase. Run apply again for the next phase.

```text
/openspec-explore How are duplicate orders handled today? Compare ways to give orders a durable id.
/openspec-propose durable-order-identity, from what we just agreed.
/openspec-apply-change durable-order-identity        # phase 1, then review and open the PRs
/openspec-apply-change durable-order-identity        # phase 2 ...
/openspec-archive-change durable-order-identity
```

`openspec/specs/` holds the main specs, updated when a change is archived.

### How much OpenSpec

OpenSpec appears in three places: the schema, `openspec/config.yaml` and the
`openspec-tracker-sync` skill. The workflow skills are OpenSpec's own, installed by
`openspec init` and not versioned here; the schema and the config change what they produce.
Two of their defaults do not apply with this schema: `openspec-propose` lists `proposal.md`,
`design.md` and `tasks.md` as the default artifacts, and `openspec-apply-change` says to continue
through every task. The schema's apply rule overrides the second in so many words.
`tests/test_openspec.py` runs the CLI against the schema, its templates and the config, so an
upgrade that stops handing them to the skills fails `make test`.

### Products

Products are optional. When `repos.json` gives repos `products`, every change belongs to exactly
one, recorded as `x-product: <slug>` in `.openspec.yaml`, and spec paths start with the slug
(`specs/<slug>/<capability>/spec.md`, `openspec/specs/<slug>/<capability>/`). A change can touch
that product's repos and the shared ones (without `products`), never two products. Without
`products` in the manifest, changes carry no `x-product` and spec paths start with the
capability. The agent never infers a product: it uses yours or the recorded one, else asks.

### Baseline specs for existing behaviour

A change can only modify or remove a requirement that already exists in `openspec/specs/`.
Behaviour built before the team adopted OpenSpec has no spec, so run
[`openspec-create-spec-from-code`](../../.agents/skills/openspec-create-spec-from-code/SKILL.md)
first, naming the capability (and the product, when there are products). Only you start it: it
writes main specs. It reads the code and tests of the repos, keeps only intended and verified
behaviour, asks about ambiguous cases in one round, and leaves the specs uncommitted for review.

### Issue tracker (optional)

One line at the top of `openspec/config.yaml` picks where phases are tracked:

```yaml
x-tracker: linear   # or github, or none
```

| `x-tracker` | Change | Phase | PR names its phase |
| --- | --- | --- | --- |
| `linear` | its own Linear project (label `Product: <slug>` when it has a product) | an issue, `[ABC-123]` | id in the title: `feat(x): ABC-123 add y` |
| `github` | a parent issue in this workspace repo | a sub-issue, `[#13]` | `Part of <owner>/<repo>#13` in the body |
| `none` | nothing | the checkboxes of `plan.md` | nothing |

With a tracker, the [`openspec-tracker-sync` skill](../../.agents/skills/openspec-tracker-sync/SKILL.md)
runs after `plan.md` is written or edited, and before archive. It writes the issue reference at
the end of the phase heading (`### Phase 1: Durable order ids [ABC-123]`) and records the
container in `.openspec.yaml` (`x-linear-project` or `x-github-issue`). When apply starts a
phase, the agent marks its issue started (In Progress in Linear, assigned to you in GitHub);
that is the only progress it writes, and you move or close issues from there. The skills read
`x-tracker` and behave the same for every tracker, so switching is that one line; `make
check` (rule `tracker`) accepts only the three values. Details per tracker are in
[`docs/agents/issue-tracker.md`](../agents/issue-tracker.md). Linear access uses the
`linear-server` MCP server (see [MCP servers](workspace.md#mcp-servers)); GitHub uses `gh`.

### Convention skills

Two skills from [CodelyTV/agent-harness](https://github.com/CodelyTV/agent-harness), pinned in
`skills-lock.json`, turn conventions into checks inside a repository instead of text an agent
may not load:

- `create-rule`: after the user corrects the agent on a convention, make it a rule (linter
  config, custom lint rule or test). When no rule can check it exactly, write a minimal doc
  with the reason it is not enforced.
- `deterministify`: enforce the conventions a repository already has, the written ones first,
  then the ones only the code shows. Claude Code never starts it on its own; every agent starts it only when the user asks. It asks before installing a dependency.

Both run inside one repository (`repos/<name>`, on a branch, reading that repo's own
instructions first); the rule, its tests and its doc are committed there and reach the default
branch through that repo's PR. A convention about this workspace that should hold in every meta
becomes a rule in the harness's `scripts/check.py` (propose it to the harness repository from a
meta; do not fork the script); one no rule can check goes to `docs/conventions/` of the meta.
`docs/agents/conventions.md` says which case is which.
