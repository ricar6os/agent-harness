# agent-harness

Skills, an [OpenSpec](https://github.com/Fission-AI/OpenSpec) schema and a multi-repo workspace
so AI agents plan and ship changes in phases you can review. Take only the part you need:

| You want | You take | How |
| -------- | -------- | --- |
| Skills in any repo | `create-pull-request`, `openspec-tracker-sync`, `unslop` | [Install the skills](#install-the-skills) |
| Lean OpenSpec changes: specs and one plan of phases | The `spec-plan` schema | [Use the schema in a repo](#use-the-schema-in-a-repo) |
| One workspace over several repos | This whole repository, as upstream | [Create a meta repo](#create-a-meta-repo) |

## Install the skills

```bash
npx skills@latest add <owner>/agent-harness
```

Pick the skills and the agents to install them on. `npx skills` copies skill folders and nothing
else: no schema, no scripts, no hooks. The skills in the "Meta workspace" group only work inside
a meta repo. `create-rule`, `deterministify` and `openspec-create-spec-from-code` come from
[CodelyTV/agent-harness](https://github.com/CodelyTV/agent-harness); install them from there.

## Use the schema in a repo

The schema is data for the OpenSpec CLI, so on its own it does nothing: the repo needs the CLI,
and the agent needs OpenSpec's workflow skills.

1. Install the CLI: `npm i -g @fission-ai/openspec`.
2. In the repo, run `openspec init --scope project --tools claude,codex`. It creates `openspec/`
   and installs OpenSpec's workflow skills (`openspec-propose`, `openspec-apply-change` and the
   others) in the repo. Without `--scope project` they are installed for the whole machine.
3. Copy the schema. From a public harness:
   `npx degit <owner>/agent-harness/openspec/schemas/spec-plan openspec/schemas/spec-plan`.
   From a private one, which `degit` cannot read, with the `gh` CLI:

   ```bash
   mkdir -p openspec/schemas/spec-plan
   gh api repos/<owner>/agent-harness/tarball \
     | tar -xz -C openspec/schemas/spec-plan --strip-components=4 '*/openspec/schemas/spec-plan'
   ```

4. Select it in `openspec/config.yaml`: `schema: spec-plan`.
5. Optional, to mirror phases to Linear or GitHub: install `openspec-tracker-sync` with
   `npx skills`, and copy `x-tracker`, `rules:` and `operations:` from this repository's
   [`openspec/config.yaml`](openspec/config.yaml).

Then `/openspec-propose` writes lean specs and one `plan.md`, `/openspec-apply-change` implements
one phase per run, and `/openspec-archive-change` merges the specs. In a single repo the plan
has no `**Repos:**` lines and nothing else changes.

## Create a meta repo

A meta is a repo with no product code that groups an organization's repositories, so agents
get organization-wide context, specs that span repos and shared skills. Each meta is a copy of
this repository that keeps its history, so harness updates arrive with a merge.

1. Create an empty private repo for the meta: `gh repo create <org>/<name> --private`.
2. Clone the harness under the meta's name and point it at the new repo, keeping the harness as
   a second remote:

   ```bash
   git clone git@github.com:<owner>/agent-harness.git <name> && cd <name>
   git remote rename origin harness
   git remote add origin git@github.com:<org>/<name>.git
   git push -u origin main
   ```

3. On a branch, edit `repos.json`: set `org`, list the repos and, if you use them, their `products`.
4. `make doctor && make sync && make check`.
5. `openspec init --scope project --tools claude,codex` installs OpenSpec's workflow skills in the
   meta. It keeps `openspec/config.yaml` as it is. Commit them, then open the meta's first PR.
6. Pick the issue tracker with `x-tracker` at the top of `openspec/config.yaml`: `linear`, `github` or `none` (see "Issue tracker" below). With Linear, the team is resolved with the user at the first sync.

## Bring harness updates into a meta

```bash
git fetch harness
git checkout -b chore/harness-update origin/main
git merge harness/main
make check && make test
```

Conflicts can only come from instance-owned files (below) or from harness files the meta
changed on purpose, such as the `x-tracker` line of step 6: keep the meta's side for those.
Open the result as a PR in the meta.

## Harness files and your files

| Harness-owned (kept identical across every meta) | Instance-owned |
| ------------------------------------------------ | -------------- |
| `scripts/`, `Makefile`, `tests/` | `repos.json` |
| `.agents/skills/` (custom and vendored) | `docs/conventions/` (workspace conventions no rule can check) |
| `.claude/`, `.opencode/`, `.github/workflows/` | `openspec/changes/`, `openspec/specs/`, the `openspec-*` skills that `openspec init` installs |
| `docs/agents/`, `openspec/schemas/`, `openspec/cli-version` | The `x-tracker` line and your own additions to the `context:` of `openspec/config.yaml` |
| MCP config files (`.mcp.json`, `.codex/config.toml`, `opencode.json`) | `env/` |
| Guardrail wiring (`.claude/settings.json`, `.codex/hooks.json`, `.opencode/plugins/guard.js`) | |

Improve harness files here first, with a PR to this repository, then merge them into each meta.

## Daily commands in a meta

```bash
make                      # list the shortcuts
make doctor               # check git, jq, gh auth, python3 and openspec
make sync                 # clone or update every repo (ONLY=a,b or PRODUCT=slug to restrict)
make status               # branch, local changes and ahead/behind of each clone
make repo-check REPO=api  # run the check command repos.json declares for a repo
make check                # check the workspace conventions
make test                 # run the tests
```

A change goes through OpenSpec's skills, one phase at a time:

```text
/openspec-explore How are duplicate orders handled today? Compare ways to give orders a durable id.
/openspec-propose durable-order-identity, from what we just agreed.
/openspec-apply-change durable-order-identity        # phase 1, then review and open the PRs
/openspec-apply-change durable-order-identity        # phase 2 ...
/openspec-archive-change durable-order-identity
```

## Reference

| Topic | Read |
| ----- | ---- |
| Layout, script flags, env files, worktrees, the `repos.json` manifest, MCP servers | [docs/reference/workspace.md](docs/reference/workspace.md) |
| The three layers, the `spec-plan` schema, products, baseline specs, the issue tracker | [docs/reference/specs.md](docs/reference/specs.md) |
| The kinds of skills and how repo skills reach the agents | [docs/reference/skills.md](docs/reference/skills.md) |
| What `make check` enforces, and how to add a rule | [docs/reference/checks.md](docs/reference/checks.md) |
| What the guardrails block, per agent | [docs/reference/guardrails.md](docs/reference/guardrails.md) |
| Instructions for agents | [AGENTS.md](AGENTS.md) and [docs/agents/](docs/agents/) |
