# agent-harness

Skills, an [OpenSpec](https://github.com/Fission-AI/OpenSpec) schema and a multi-repo workspace
so AI agents plan and ship changes in phases you can review. How you set it up depends on the
repo:

| Your repo is | Set it up with |
| ------------ | -------------- |
| A product repo: one repo with code | [Set up a product repo](#set-up-a-product-repo): the skills with `npx skills`, the schema with OpenSpec |
| A new workspace over several repos | [Set up a new meta repo](#set-up-a-new-meta-repo): a clone of this repository, as upstream |
| A meta created from the old template | [Adopt the harness in an existing meta](#adopt-the-harness-in-an-existing-meta): one merge |

Copy no files by hand in any of the three. A clone keeps the history that later updates merge
through, and `npx skills` records what it installed in `skills-lock.json`.

## Set up a product repo

Run every command from the root of the repo. Nothing of this repository is copied except the
skills you pick and the schema folder.

### 1. The skills

```bash
npx skills@latest add <owner>/agent-harness --skill create-pull-request openspec-tracker-sync unslop
```

It asks which agents to install them on, writes the skills to `.agents/skills/`, links them for
each agent and records them in `skills-lock.json`. Commit all of it. Leave `--skill` out to pick
from the list; the skills of its "Meta workspace" group only work inside a meta repo.
`npx skills update` brings later versions.

The skills this harness takes from Codely are installed from their repository:

```bash
npx skills@latest add codelytv/agent-harness --skill create-rule deterministify openspec-create-spec-from-code
```

### 2. OpenSpec and the schema

The schema is data for the OpenSpec CLI, so on its own it does nothing: the repo needs the CLI,
and the agent needs OpenSpec's workflow skills.

```bash
npm i -g @fission-ai/openspec
openspec init --scope project --tools claude,codex

mkdir -p openspec/schemas/spec-plan
gh api repos/<owner>/agent-harness/tarball \
  | tar -xz -C openspec/schemas/spec-plan --strip-components=4 '*/openspec/schemas/spec-plan'
```

Then set `schema: spec-plan` in `openspec/config.yaml`, and commit `openspec/` and the skills.

- `openspec init` creates `openspec/` and installs OpenSpec's workflow skills
  (`openspec-propose`, `openspec-apply-change` and the others) in the repo. Without
  `--scope project` it installs them for the whole machine instead.
- The `gh` command copies the schema from a private harness. From a public one,
  `npx degit <owner>/agent-harness/openspec/schemas/spec-plan openspec/schemas/spec-plan` does
  the same; `degit` cannot read a private repository.

### 3. The tracker (optional)

To mirror the phases of a plan to Linear or GitHub, copy `x-tracker`, `rules:` and `operations:`
from this repository's [`openspec/config.yaml`](openspec/config.yaml) into yours, and set
`x-tracker` to `linear` or `github`. Without them, the checkboxes of `plan.md` are the tracking.

### 4. Use it

`/openspec-propose` writes lean specs and one `plan.md`, `/openspec-apply-change` implements one
phase per run and stops, and `/openspec-archive-change` merges the specs. `/create-pull-request`
writes the PR of each phase. In a single repo the plan has no `**Repos:**` lines.

## Set up a new meta repo

A meta is a repo with no product code that groups an organization's repositories, so agents
get organization-wide context, specs that span repos and shared skills. It is a clone of this
repository that keeps its history: clone it, never copy its files, so that harness updates
arrive with a merge.

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
6. Pick the issue tracker with `x-tracker` at the top of `openspec/config.yaml`: `linear`,
   `github` or `none` (see [the specs reference](docs/reference/specs.md)). With Linear, the team
   is resolved with the user at the first sync.

The skills, the schema and the scripts come with the clone: a meta needs no `npx skills`.

## Adopt the harness in an existing meta

A meta created from the old GitHub template has the harness's files and none of its history.
One merge joins the two; after it, updates are plain merges.

```bash
git remote add harness git@github.com:<owner>/agent-harness.git
git fetch harness
git checkout -b chore/adopt-harness

# 1. Take the harness's version of every file both sides have.
git merge harness/main --allow-unrelated-histories -X theirs --no-commit

# 2. Take back your own files that the merge overwrote.
git checkout HEAD -- repos.json

# 3. Remove what the harness deleted since the template (old skills, the glossary map).
root=$(git rev-list --max-parents=0 harness/main)
git diff -z --name-only --diff-filter=D "$root" harness/main | xargs -0 git rm -q --ignore-unmatch --

git status                      # review before committing
git commit -m "chore: adopt the agent-harness upstream"
make check && make test
openspec init --scope project --tools claude,codex
```

- Step 2 names the instance-owned files that exist on both sides. `repos.json` is the usual
  one; add `openspec/config.yaml` when you changed it and want your version back. Files only
  you have (`openspec/changes/`, `openspec/specs/`, `docs/conventions/`, `env/`) are not touched.
- Step 3 also removes `GLOSSARY-MAP.md` and the old `openspec-*` skills. To keep a file you
  still use, bring it back before committing: `git checkout HEAD -- GLOSSARY-MAP.md`.
- A change in flight keeps its artifacts: each change records its schema in `.openspec.yaml`.

Open the branch as a PR in the meta.

## Bring harness updates into a meta

```bash
git fetch harness
git checkout -b chore/harness-update origin/main
git merge harness/main
make check && make test
```

Conflicts can only come from instance-owned files (below) or from harness files the meta
changed on purpose, such as the `x-tracker` line: keep the meta's side for those. Open the
result as a PR in the meta.

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
