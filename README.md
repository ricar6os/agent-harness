# agent-harness

This repository is a template for meta workspaces: a repo with no product code that groups an
organization's repositories so AI agents get organization-wide context, cross-repo
[OpenSpec](https://github.com/Fission-AI/OpenSpec) specs and shared skills.

## Create a meta repo from this template

1. `gh repo create <org>/<name> --template <owner>/agent-harness --private --clone`
2. Edit `repos.json`: set `org`, list the repos and their `products`.
3. `make doctor && make sync && make check`
4. Fill `GLOSSARY-MAP.md`. (The Linear team is resolved with the user at the first sync.)

## Harness files and your files

| Harness-owned (kept identical across every meta) | Instance-owned |
| ------------------------------------------------ | -------------- |
| `scripts/`, `Makefile`, `tests/` | `repos.json` |
| `.agents/skills/` (custom, vendored and generated) | `GLOSSARY-MAP.md` |
| `.claude/`, `.opencode/`, `.github/workflows/` | `docs/contexts/` |
| `docs/agents/`, `openspec/config.yaml`, `openspec/cli-profile.json` | `docs/conventions/` (workspace conventions no rule can check), `openspec/changes/`, `openspec/specs/` |
| MCP config files (`.mcp.json`, `.codex/config.toml`, `opencode.json`) | `env/` |
| Guardrail wiring (`.claude/settings.json`, `.codex/hooks.json`, `.opencode/plugins/guard.js`) | |

Improve harness files in the template first, then bring them to each meta.

## What a meta repo does

Workspace that groups every repository of the organization in `repos.json` in order to:

- launch AI agents with organization-wide context,
- write specs that involve several repos (via [OpenSpec](https://github.com/Fission-AI/OpenSpec)),
- share cross-cutting skills (root level) alongside each repo's own skills.

All code, comments and documentation in this repo are written in English (see `AGENTS.md`).

## Layout

```
repos.json               manifest: which repos to clone and on which branch
Makefile                 shortcuts for the commands below (`make` lists them)
scripts/init.sh          clone/update the repos from the manifest into repos/
scripts/status.sh        branch, local changes, ahead/behind, instructions and check command of each cloned repo
scripts/repo-check.sh    run a repo's `check` command from the manifest inside its clone (`make repo-check REPO=<name>`)
scripts/link-skills.sh   link each repo's skills into .claude/skills/ and .agents/skills/ (run by init.sh)
scripts/check.py         deterministic convention checks (`make check`)
scripts/guard.py         agent guardrails: decides each tool call (see "Guardrails")
scripts/openspec-update.sh  regenerate the openspec-* skills with the pinned CLI version and profile
tests/                   unit tests of the checker and the guardrails (`make test`)
.github/workflows/check.yml  runs the checks and the tests on every pull request
repos/<name>/            org repos (git-ignored; each one is its own git repository)
env/<name>/              local .env/secret files symlinked into repos/<name>/ by init.sh (git-ignored)
openspec/                OpenSpec: config.yaml, cli-version (pinned CLI version), cli-profile.json (pinned CLI profile), changes/ (in-flight work), specs/ (main specs)
.agents/skills/          root-level skills — canonical location (Codex/ChatGPT + Claude Code)
.claude/skills/          Claude Code skills: symlinks to .agents/skills/ for every skill (custom, vendored and generated)
.mcp.json                project MCP servers (Linear)
.claude/settings.json    Claude Code hook that runs scripts/guard.py
.codex/hooks.json        Codex hook that runs scripts/guard.py
.opencode/plugins/guard.js  OpenCode plugin that runs scripts/guard.py
AGENTS.md                instructions for AI agents (Claude Code, Codex and OpenCode load it directly; there is no CLAUDE.md)
```

## Getting started

```bash
make                         # list the available shortcuts
make doctor                  # check git, jq, gh auth, python3 and openspec are available
make sync                    # clone/update every repo from repos.json into repos/
make sync ONLY=api,web   # restrict to some repos
make sync PRODUCT=shop      # restrict to the repos of an OpenSpec product
make status                  # status of each cloned repo
make list                    # print the manifest
make repo-check REPO=api     # run the check command that repos.json declares for a repo (one repo name, nothing after it)
make openspec                # regenerate the openspec-* skills with the pinned CLI version and profile
make check                   # check the workspace conventions (see "Checks")
make test                    # run the tests of the checker and the guardrails
```

The targets are thin wrappers around `scripts/`; call the scripts directly for extra flags:

```bash
scripts/init.sh              # clone every repo from repos.json into repos/
scripts/init.sh --only api,web
scripts/init.sh --product shop
scripts/init.sh --no-update  # leave already-cloned repos untouched
scripts/init.sh --list       # print the manifest
CLONE_DEPTH=1 scripts/init.sh
META_REPO_WORKTREES=0 scripts/init.sh  # in a meta worktree, clone instead of adding worktrees
META_ENV_DIR=/path scripts/init.sh  # use another env/ directory
scripts/status.sh            # status of each cloned repo
```

### Local env files and secrets

Repos such as `api` (`.env`) and `web` (`.env.secrets`) need files that are git-ignored in
their own repository. Put them under `env/<name>/`:

```
env/api/.env
env/web/.env.secrets
```

`scripts/init.sh` symlinks every file there into `repos/<name>/` after cloning or updating.
It reads `env/` of the main checkout first (found through `git rev-parse --git-common-dir`,
so a fresh worktree created with `git worktree add` or a tool that wraps it links the same
files without copying them) and then `env/` of the current checkout, which wins. A regular
file already present in the repo is never overwritten. Everything under `env/<name>/` except
`.gitkeep` is git-ignored. See `env/README.md`.

### Repos in a meta worktree

Run `make sync` in a fresh meta worktree (for example one per agent session) and each repo that
the main checkout has cloned is added as a git worktree of that clone instead of cloned again:
it takes seconds, shares the object store, and gives the session its own checkout, so parallel
sessions never edit the same files. The repo starts detached at `origin/<branch>`; create a
branch before committing (step 3 of [`docs/agents/working-on-a-repo.md`](docs/agents/working-on-a-repo.md)). Removing the meta
worktree leaves a stale entry in the main clone, which the next sync prunes. Set
`META_REPO_WORKTREES=0` to clone instead.

Requirements: `git`, `jq`, `python3` (3.9 or newer, standard library only), SSH access to GitHub
(`gh auth status`) and the `openspec` CLI at the pinned version (`npm i -g "@fission-ai/openspec@$(cat openspec/cli-version)"`) for the spec workflow.

## Checks

Conventions that can be verified without judgement are enforced by `make check`
(`scripts/check.py`, Python standard library only). It needs no clone under `repos/`, runs in
seconds and prints one line per violation, saying what is wrong and what to do instead, then
the place where the convention is written. Run `python3 scripts/check.py --list` for the rules,
`--only a,b` to run some, `--root DIR` to check another workspace.

| Rule | What it enforces | Convention |
| ---- | ---------------- | ---------- |
| `manifest` | `repos.json` has only known keys, valid `products` slugs, and unique names and paths | [Manifest](#manifest-reposjson) |
| `change-product` | every change records a product known to `repos.json`; delta and main specs sit under that product; no Linear project is shared between changes | [`docs/agents/openspec.md`](docs/agents/openspec.md), "Products and Linear projects" |
| `task-dependencies` | `Depends on:` references in `tasks.md` exist, and no cycle among tasks and groups (a group waits for all its tasks) can deadlock them | [`openspec-linear-sync`](.agents/skills/openspec-linear-sync/SKILL.md), "Dependencies" |
| `mcp-parity` | every MCP server is declared, with the same url, in `.mcp.json`, `.codex/config.toml` and `opencode.json` | [MCP servers](#mcp-servers) |
| `skill-exposure` | each custom skill has valid frontmatter and is visible to Claude Code; no broken links; `skills-lock.json` matches | [`docs/agents/workspace-changes.md`](docs/agents/workspace-changes.md), "Custom skills" |
| `tracked-secrets` | git tracks no env file, nothing under `env/` except placeholders, nothing under the clones directory | `env/README.md` |
| `generated-skills` | running `make openspec` on a clean copy changes nothing under `.agents/` and `.claude/`: no generated file is edited, missing or stale | [`docs/agents/workspace-changes.md`](docs/agents/workspace-changes.md), "Generated files" |
| `openspec-validate` | `openspec validate --all --strict` passes, with the CLI at the pinned version when `openspec/cli-version` exists; a workspace without `openspec/` has nothing to validate | `openspec/config.yaml` |
| `agents-map` | `AGENTS.md` exists and is at most 6000 bytes; every `docs/agents/*.md` is linked from it; every relative Markdown link in `AGENTS.md` and `docs/agents/*.md` resolves | [AGENTS.md is a map](#agentsmd-is-a-map) |
| `guardrails` | `scripts/guard.py` is executable; `.claude/settings.json` and `.codex/hooks.json` have a `PreToolUse` hook on `Bash` that runs it with `--agent claude` / `--agent codex`; the OpenCode plugin's code (comments stripped) runs it with `--agent opencode` in a `tool.execute.before` hook | [Guardrails](#guardrails) |

A rule skips, and says so, when it cannot run: the `openspec` CLI is missing or is not the
pinned version (`generated-skills`, and `openspec-validate` when `openspec/cli-version` exists; without that file `openspec-validate` uses whatever CLI is installed), or the directory is not a git work tree, or (`mcp-parity`, on Python 3.9 and 3.10 only) `.codex/config.toml` uses TOML the built-in fallback parser does not implement (triple-quoted strings, `[[mcp_servers...]]` headers, escapes in a url or a name) and needs Python 3.11+. With `--require-tools`, a missing or
wrong tool, or such a file, is a violation instead; CI uses it, so a skip never hides a failure there.

The OpenSpec CLI version is pinned in `openspec/cli-version` (one version number, for example
`2.1.1`), and `scripts/check.py --openspec-version` prints it; CI installs exactly that version.
The profile the CLI generates with is pinned in `openspec/cli-profile.json`, and
`skillsScope: project` in `openspec/config.yaml` keeps the generated skills in this repo so every
clone and CI gets the same ones. `make openspec` applies them (through
`scripts/openspec-update.sh`, which refuses to run with another CLI version and never touches
your own CLI configuration), so every meta generates the same files. To upgrade OpenSpec, write
the new version in `openspec/cli-version`, install that version, run `make openspec`, run
`make check` and commit.

CI (`.github/workflows/check.yml`) runs `scripts/check.py --require-tools` and the tests on
every pull request and on pushes to `main`.

### AGENTS.md is a map

Every agent loads `AGENTS.md` at the start of every session, so it holds only the rules that must
hold in every session and a map saying which file to read for which task. It is capped at 6000
bytes (rule `agents-map`). Detail lives in `docs/agents/`, one short file per topic, and each
file is linked from `AGENTS.md` with a line saying when to read it. Relative links in these files
must resolve. A rule stated in full where it is used (`openspec/config.yaml` for OpenSpec
operations, a skill for its task) is pointed to, not copied.

### Adding a rule

1. Report only what is certainly wrong: if a case cannot be decided exactly, skip it.
2. Make the message say what to do instead, not only what is wrong.
3. Name where the convention is written in the rule's `convention` text, and write it there if it is not.
4. Add a test that sees each kind of violation fail, and one that passes, in `tests/test_check.py`.
5. Keep the whole run in seconds and independent of `repos/`.

## Guardrails

`AGENTS.md` asks agents to ask first before merging, force-pushing or deleting branches, never to
commit to a default branch and never to put secrets in the conversation. The parts of that a
tool-call hook can decide exactly are enforced by `scripts/guard.py` (Python standard library
only): one function, `decide(tool, tool_input, cwd, root)`, answers `allow`, `ask` or `deny` with
a reason, and a thin adapter per agent speaks that agent's hook format. The rule is **exact or
skip**: it blocks only what is certainly the forbidden action, because a guard that guesses
trains people to bypass it. An internal error allows the call and prints one line on stderr.

| Decision | What | Why the agent is told |
| -------- | ---- | --------------------- |
| ask | `git push` with `--force`, `-f`, `--force-with-lease`, `--force-if-includes` or a `+refspec` | force-push rewrites remote history |
| ask | `git push --delete`/`-d` or a `:branch` refspec | deletes a remote branch |
| ask | `git branch -d`/`-D`/`--delete` | deletes a branch |
| ask | `gh pr merge`, also behind global flags (`gh -R owner/repo pr merge 12`); `--help` is allowed | merging is the user's decision |
| deny | `git commit` on the default branch of the target repository | create a branch first (`git -C <dir> checkout -b <type>/<short-slug>`) |
| deny | `git push` from the default branch, or to it (`main`, `HEAD:main`, `x:main`) | open a PR instead |
| deny | reading or writing a secret file (`env/**` except `env/README.md` and `.gitkeep`; `.env`, `.env.*` except `.example`, `.sample`, `.template`, `.dist`; names are matched case-insensitively, as macOS file systems are) with a file tool (`Write`, `Edit`, `apply_patch` included), or printing it with `cat`, `grep`, `sed`, `jq`, `open`, `vim` and similar | secret values stay out of the conversation; read the `.example` template |
| deny | `env`, `printenv`, `export` or `export -p`, `declare -x`, `set` with no arguments | dumps every variable, tokens included; use `printenv NAME` |

The default branch of a clone is the `branch` of its `repos.json` entry (`main` when omitted);
anywhere else it is `origin/HEAD`, or `main`/`master` when that is the current branch. Outside a
git repository, on a detached HEAD, or when the branch cannot be told, nothing is blocked. A
commit or push that follows `git checkout <branch>`, `git checkout -b`, `git switch <branch>`, `git switch -c`
or `git checkout -t origin/<branch>` in the same command line counts as running on that branch (a name that is
a file and not a branch, `.`, `HEAD~1`, `-`, `--detach`, `git checkout -p` or `git checkout <tree-ish> -- <paths>` leaves it as it was or unknown). A new repository with no commit
and no `origin` has nothing to protect: its first commit is allowed. `cd <dir>` and `git -C <dir>` are followed,
as are `( ... )` subshells (only an unquoted parenthesis where a command starts opens one; a `)` in a quoted message or in `$( ... )` does not close it), `{ ...; }` groups, the commands after `do`, `then` and `else`, the command that `env [NAME=value] ...` wraps, and `bash -c '<literal string>'` (a checkout inside them counts for the rest of the line, a `cd` does not); redirections such as `2>&1` are not arguments; heredoc bodies are data and are not read as commands, unless the heredoc feeds a shell (`sh <<EOF`, `bash -s arg <<EOF`, `cat <<EOF | bash`), whose body is read like `bash -c`.
`git push --tags` alone is allowed; `--follow-tags` pushes the branch too. Moving,
copying, linking, removing, `source`-ing a secret file or passing it to `--env-file` is allowed:
those do not print values.

| Agent | Enforced through | `ask` |
| ----- | ---------------- | ----- |
| Claude Code | `.claude/settings.json`, a `PreToolUse` hook on `Bash`, `Read`, `Edit`, `Write`, `MultiEdit` and `NotebookEdit` | the user is prompted to confirm |
| Codex | `.codex/hooks.json`, a `PreToolUse` hook on shell commands and `apply_patch`; the hook walks up from the session directory to the nearest folder holding `repos.json` and `scripts/guard.py`, so it runs this workspace's script even from inside `repos/<name>`, and does nothing when there is none. Codex loads project hooks only from a trusted project and asks you to review the hook (`/hooks`) once | hooks cannot ask: the call is blocked with a reason telling the agent to ask you to run the command or confirm |
| OpenCode | `.opencode/plugins/guard.js`, a plugin hook on `tool.execute.before`. A plain object with no package import, only Node built-ins (see below) | same as Codex: blocked, with the same reason |

Any other agent is not enforced.

A blocked call means stop and ask the user; look for no other route to the same effect. To see why
a command is blocked, or whether it would be:

```bash
scripts/guard.py --explain 'git push --force origin main'   # prints "deny: ..." / "ask: ..." / "allow"
```

`--explain` runs the command as if typed in the current directory (it follows `cd` and `git -C`).

Deliberately **not** enforced, because no hook can decide it exactly: changes to production
infrastructure, removing entries from `repos.json`, and secrets printed by a program the agent
runs (a script that echoes its `.env`, `docker inspect`, a server log). Those stay with the
"ask first" list in `AGENTS.md`. Also out of reach: commands built at run time (`bash -c "$X"`, a
`bash -c` string with `$` or a backtick inside, `eval`, `$(...)`, `xargs`), a script file the agent writes and
then runs, and anything an agent does through another tool. This prevents mistakes; it is not a
sandbox, and a determined agent or person can get around it.

OpenCode plugin, verified with OpenCode 2.3.2 (macOS, a throwaway copy of this repo with no
`node_modules`, model `opencode/deepseek-v4.1-flash-free`): the plugin loaded and blocked a
`git push --force origin feat/x` on a feature branch, and the agent was told "force-push rewrites
remote history: confirm with the user. Blocked: ...". The previous form, which imported `@opencode/plugin`, also
loaded in that version, but the real package is `@opencode-ai/plugin`, so the import would fail on other
versions; the plugin is now a plain `export default { id, setup }` object with no package import (only Node built-ins), and that form
blocked the same call. OpenCode created nothing inside the project (no `.opencode/package.json`, `node_modules`,
lock file or `.gitignore`), so nothing is ignored or committed for it. It only wrote its own state under
`~/.local/share/opencode` and `~/.local/state/opencode`. Other OpenCode versions were not tried.

The `guardrails` check keeps the wiring in place. Changes to `scripts/guard.py` come with rows in
`tests/test_guard.py`: one for what it blocks and one for the look-alike it must still allow.

## Manifest (`repos.json`)

```json
{
  "org": "your-org",
  "root": "repos",
  "repos": [
    {
      "name": "api",
      "url": "git@github.com:your-org/api.git",
      "branch": "main",
      "description": "Internal API",
      "path": "api",
      "products": ["shop"],
      "check": "pnpm test"
    }
  ]
}
```

`check` is optional: the one command a contributor runs inside the repo to verify a change (lint,
types, tests). `make repo-check REPO=<name>` runs it there, `make list` shows it, and `make status`
flags the repos that declare none. `path` is optional (defaults to `name`) and, like `name`, must be a single directory name: clones live directly under the repos directory. `products` lists the OpenSpec products
the repo belongs to, by slug (the same product a change records as `x-product` in `.openspec.yaml`); a repo
without `products` is shared by every product. This is the only place that ties repos to products: `make sync
PRODUCT=<slug>` and the OpenSpec workflow read it from here. Add or remove entries to control
what gets cloned. `scripts/init.sh` never resets a repo with local changes (fetch only).

## Specs (OpenSpec)

Domain documentation uses a [glossary map](GLOSSARY-MAP.md), organized by the products
in `repos.json` and linked to their repository-local glossaries. Read only the contexts
relevant to the work; [domain consumer rules](docs/agents/domain.md) describe where vocabulary,
specifications and decisions belong.

Cross-repo specs are managed with OpenSpec under `openspec/`:

- `openspec/changes/<change>/` — proposal, design, delta specs and tasks for work in flight.
- `openspec/specs/` — the main, always-current specs (updated when a change is synced/archived).
- `openspec/config.yaml` — product rules, context and per-artifact rules shown to the AI.

Specs are split by **OpenSpec product**, such as `shop`. Every change belongs to
exactly one product, recorded as `x-product: <slug>` in `.openspec.yaml`. OpenSpec 2 warns about unknown
keys, and strict validation fails on them, so the metadata keys carry the `x-` prefix. Capability paths
start with that slug: `specs/<slug>/<capability>/spec.md` in a change and
`openspec/specs/<slug>/<capability>/` for main specs. A change may affect multiple repositories
of its product, including shared repos within that scope, but never multiple products.
Split work spanning products into separate changes.

Each change corresponds one-to-one to a **Linear project**, recorded separately as
`x-linear-project: {id, url}`. That project's label under the group **Product** identifies
the OpenSpec product. Several Linear projects can carry `Product: Shop`, each representing
a different change; they all use the `shop` spec namespace.

OpenSpec operations use the product you name or the change's recorded `x-product`; if missing,
the agent lists workspace products and asks. Linear synchronization separately resolves your
chosen Linear project or its recorded id, and asks when neither exists. New Linear projects
are created only when requested, with the team resolved. Local planning can begin before a
Linear project is selected; publishing tasks requires the binding.

Typical flow from Claude Code: `/openspec-explore` → `/openspec-propose` → `/openspec-apply-change` →
`/openspec-archive-change` (`/openspec-update-change` revises a plan, `/openspec-sync-specs` pushes
delta specs to the main specs). The same workflow is available to Codex/ChatGPT through the
`openspec-*` skills in `.agents/skills/`.

A change that spans several repos needs a `design.md` with a `## Contracts` section (each contract
that crosses a repo boundary, as its consumer sees it: endpoint method, path and fields, event
payload, table columns, package signatures; also an old shape the provider keeps alive for a
transition) and a `## Deployment order` section (one ordered list of repos per phase when the
change ships in phases; each step names what must already be deployed; a transition states the
condition that ends it, such as a later phase or a release). Its tasks verify their side of a
contract against that section and are implemented one repo at a time with one PR per repo (see
[`docs/agents/working-on-a-repo.md`](docs/agents/working-on-a-repo.md)). The exact wording is in
`openspec/config.yaml`.

### Creating specs with explore, grill-with-docs and propose

Use these skills from the meta workspace, naming the OpenSpec product in your request. Start
with the problem, the intended outcome and any constraints; the agent reads
`GLOSSARY-MAP.md`, the relevant glossaries, existing specs and repository code for context.

| Skill | When to use it | Result |
| ----- | -------------- | ------ |
| [`openspec-explore`](.agents/skills/openspec-explore/SKILL.md) | Understand the current behavior, investigate a problem or compare approaches. | A clearer scope, options and open questions. It does not implement code or automatically produce a complete spec. Ask explicitly to save findings as OpenSpec artifacts. |
| [`grill-with-docs`](.agents/skills/grill-with-docs/SKILL.md) | Challenge an idea or design before committing to it. | Combines `grilling` and `domain-modeling`: questions in rounds, recommended answers, resolved glossary terms and ADRs when a decision warrants one. |
| [`openspec-propose`](.agents/skills/openspec-propose/SKILL.md) | Turn an agreed direction into a change ready for review and implementation. | Creates the change metadata, proposal, delta specs, design when applicable and implementation tasks. It stops after planning. |

A useful sequence is **explore → grill-with-docs → propose**. The first two are optional:
start with `grill-with-docs` if you already have a concrete design, return to `explore` when
questions need investigation, or go straight to `propose` when the scope is clear.

For example, send these as separate messages in the same Claude Code conversation, answering
the questions and confirming the agreed scope before moving on:

```text
/openspec-explore For OpenSpec product shop, investigate how duplicate orders are handled today.
Compare ways to give each order a durable identity across systems.

/grill-with-docs For OpenSpec product shop, challenge the order identity approach we just explored.
Resolve identity rules, merge edge cases, scope and acceptance criteria. Record agreed
domain terms in the product glossary and offer ADRs for significant trade-offs.

/openspec-propose Create change durable-order-identity for OpenSpec product shop using our agreed
decisions. Include requirements and scenarios, affected repos and contracts, deployment
order and implementation tasks. Group tasks by a common objective, with each task ready
to become an individual issue. Before publishing to Linear, ask me to select or create
a dedicated project for this change and resolve its team.
```

In Codex/ChatGPT, request the corresponding skills by name: "Use `openspec-explore` for
OpenSpec product shop to investigate…", "Use `grill-with-docs` to challenge this approach…", then
"Use `openspec-propose` to create…". If `grill-with-docs` is not exposed in the client's
skill picker, ask the agent to read `.agents/skills/grill-with-docs/SKILL.md` and use its
`grilling` and `domain-modeling` skills together. In a new conversation, provide links to
the saved findings and decisions so the proposal can use them.

The documents serve different purposes. Glossaries contain domain vocabulary; ADRs explain
significant decisions. Follow [the domain documentation rules](docs/agents/domain.md) for
their product or repository scope. Requirements and scenarios belong in the change's delta
specs, under `openspec/changes/<change>/specs/<product>/<capability>/spec.md`, alongside
`proposal.md`, `design.md` and `tasks.md`. Creating a proposal does not update the main specs.

Review the generated requirements, scenarios, design and tasks before requesting
`/openspec-apply-change <change>`. If the plan needs revision, use
`/openspec-update-change <change>`. Creating or updating `tasks.md` also
triggers the Linear synchronization described below.

### Baseline specs for existing behaviour

A change can only modify or remove a requirement that already exists in `openspec/specs/`.
Behaviour built before the team adopted OpenSpec has no spec, so a change over it would add
requirements and never record what was there before. Run
[`openspec-create-spec-from-code`](.agents/skills/openspec-create-spec-from-code/SKILL.md)
first, naming the OpenSpec product and a capability (or a change you are about to make, or
"which features have no spec?"). Only you start it: it writes main specs.

The agent syncs the product's repos, explores the code and tests of each area, and separates
what was intended and verified from bugs, accidents and dead code. It asks you about the
ambiguous cases in one round. The result is `openspec/specs/<product>/<capability>/spec.md`,
validated in strict mode, left uncommitted for your review, plus a report of the drift,
the bugs it left out and the terms the product glossary lacks. Commit the specs in this
workspace on a branch, then go on with `/openspec-explore` or `/openspec-propose`.

### Linear integration

The [`openspec-linear-sync` skill](.agents/skills/openspec-linear-sync/SKILL.md) runs after
`tasks.md` is created or updated, and before archive.
It uses this hierarchy:

```text
OpenSpec product: shop
└── Change: durable-order-identity → its own Linear project, labelled Product: Shop
    ├── Epic issue: Give orders durable identities
    │   ├── Task issue: Add persistent identifiers
    │   └── Task issue: Expose identifiers in the API
    └── Epic issue: Resolve duplicate orders
        ├── Task issue: Detect duplicate candidates
        └── Task issue: Merge confirmed duplicates
```

The change maps to the Linear project itself. Each numbered `## N. <objective>` task group
becomes an issue labelled `Epic`; every numbered checkbox becomes an individual child issue,
explicitly assigned to the same Linear project. The Epic describes the common objective and
completion criteria; task issues include their acceptance criteria and source links. There
is no Story layer, and the tasks are not reduced to a checklist inside another issue.

`Product` is a **project-label group**. The selected Linear project carries exactly one label
in that group, matching the OpenSpec product; other project labels are preserved. The agent
ensures the group and matching label during synchronization, using available MCP operations.
A conflicting Product label is reconciled with you before reclassification.

The binding uses real values returned by Linear; the following is a format example:

```yaml
x-product: shop
x-linear-project:
  id: <actual Linear project UUID>
  url: <actual Linear project URL>
x-linear-sync-version: 2
```

Issue ids are saved next to their group or task in `tasks.md` (illustrative ids below):

```markdown
## 1. Give orders durable identities [ABC-123]

- [ ] 1.1 Add persistent identifiers; verify uniqueness [ABC-124] <!-- in-progress -->
- [x] 1.2 Expose identifiers in the API; verify response contract [ABC-125]
```

Task ids are used in PR titles. Apply adds the `<!-- in-progress -->` marker when work
starts and removes it when checking the task off; both are local progress in `tasks.md`.
When apply starts a task that has an issue id, the agent moves that issue and its parent
Epic to In Progress if they are still in Backlog or Todo. That is the only Linear status the
agent writes, and from there you move the cards. Checking a task off leaves Linear
unchanged, and a sync only reports differences between the file and Linear. Linear project
status remains separately managed.

Existing ids are reused, and an unchanged sync performs no writes. The old `Linear epic:`
header and Story-based annotations require an explicit migration before reuse. Existing
changes with only `x-product: shop` retain their product; their first sync must resolve a
separate Linear project. The skill documents the migration and recovery rules.

Linear access uses the `linear-server` MCP server (see "MCP servers" below and
`docs/agents/issue-tracker.md`); authenticate once per client before the first sync. If a
required project-label/group operation is unavailable, the agent reports that limitation
and keeps the local artifacts pending synchronization.

### Planning and research skills

The workspace keeps a small subset of
[mattpocock/skills](https://github.com/mattpocock/skills), pinned in `skills-lock.json`:

- `grill-with-docs` combines `grilling` and `domain-modeling` to stress-test a design while
  recording vocabulary and durable decisions.
- `research` investigates documentation and APIs against primary sources.

OpenSpec remains the shared workflow for proposals, specifications, tasks, implementation and
Linear synchronization. Generic engineering skills belong in each developer's personal setup
unless the team adopts them as a repository convention.

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
becomes a rule in the template's `scripts/check.py` (propose it to the template from a meta; do
not fork the script); one no rule can check goes to `docs/conventions/` of the meta.
`docs/agents/conventions.md` says which case is which.

## Skills

- **Root skills** live in `.agents/skills/` (canonical). Three kinds:
  - _Custom_ (e.g. `sync-repos`): `SKILL.md` + `agents/openai.yaml`. Exposed to Claude Code with a
    relative symlink: `mkdir -p .claude/skills/<name> && ln -s ../../../.agents/skills/<name>/SKILL.md .claude/skills/<name>/SKILL.md`.
    `create-pull-request` (adapted from CodelyTV/agent-harness, MIT) writes the title and body of a PR
    with evidence, deploy steps, rollback and links between the PRs of a multi-repo change.
    `openspec-create-spec-from-code` (adapted from CodelyTV/agent-harness, MIT) writes the baseline main specs of a
    product's existing behaviour from the code of its repos, so the first change over it can modify or remove
    requirements. Only the user starts it.
  - _Vendored_ (`grill-with-docs`, `grilling`, `domain-modeling`, `research` from
    [mattpocock/skills](https://github.com/mattpocock/skills); `create-rule`, `deterministify` from
    [CodelyTV/agent-harness](https://github.com/CodelyTV/agent-harness)): selected upstream
    skills pinned in `skills-lock.json` and exposed through directory symlinks in `.claude/skills/`.
  - _Generated_ (`openspec-*`): written by `make openspec` into `.agents/skills/`, with a
    directory symlink for each in `.claude/skills/`. The CLI version and profile are pinned in
    `openspec/cli-version` and `openspec/cli-profile.json`. Do not edit by hand; re-run `make openspec`.
- **Per-repo skills**: `repos/<name>/.agents/skills/` (or `.claude/skills/`), owned by each
  repository. Neither tool offers them from the meta root on its own: Claude Code loads skills
  below the start directory only once it touches a file there (and in our tests never from the
  git-ignored `repos/`), and Codex only reads `.agents/skills/` from the working directory
  upwards. `make sync` (or `make skills` alone)
  runs `scripts/link-skills.sh`, which links each one as `<repo>--<skill>` into
  `.claude/skills/` and `.agents/skills/` (git-ignored; the repo keeps the only copy). A git
  worktree without its own clone of a repo links to the main checkout's clone. Both tools name
  a skill after its frontmatter, so each name is linked once: meta's own skill wins, and among
  repos the copy with the most recent commit wins; the script prints each skipped skill. A
  skill that several repos install from the same `skills-lock.json` source is linked as
  `shared--<skill>`, since it belongs to none of them.
- **Per-repo instructions**: from the meta root, Codex never loads `repos/<name>/AGENTS.md`, and
  Claude Code attaches it to a tool result that models sometimes discard. So the same script
  generates a `<repo>--instructions` skill for each clone that is in the manifest and has
  instructions (an `AGENTS.md`, or a `CLAUDE.md` with more than an `@AGENTS.md` import) or a
  `check` command, and for each clone that is not in the manifest but has instructions. It tells
  the agent to read those files and, when a `check` is declared, to verify changes with
  `make repo-check REPO=<name>` (in a worktree that has not cloned the repo, it says to run
  `make sync ONLY=<name>` first). A manifest repo with a `check` but no instructions gets a skill
  that says it has no `AGENTS.md`. A clone with neither instructions nor a `check` gets no skill;
  `make status` lists it as without instructions. Skills are listed up front by
  every harness, so this works the same in Claude Code, Codex and others. Start a new agent
  session after linking to pick up new skills.

## Working on repos

AI agents can edit code, commit and open PRs in every cloned repo. Each `repos/<name>` is an
independent git repository: branch, commit and `gh pr create` from inside it, one PR per repo.
The full workflow is described in [`docs/agents/working-on-a-repo.md`](docs/agents/working-on-a-repo.md).

### MCP servers

Same server, same name (`linear-server`), one file per client — all three are versioned and must
stay in sync:

| Client      | File                 |
| ----------- | -------------------- |
| Claude Code | `.mcp.json`          |
| Codex       | `.codex/config.toml` |
| opencode    | `opencode.json`      |

Adding or removing a server means editing all three. Keep them to what the whole team needs:
personal servers and preferences go in the per-user config (`~/.claude/settings.json`,
`~/.codex/config.toml`, `~/.config/opencode/opencode.json`), never here.

Codex only loads `.codex/config.toml` once the repository is **trusted** — it prompts on the first
run in a new clone. Until then Codex sees no project MCP servers. Claude Code asks for approval of
`.mcp.json` on first use and records per-developer overrides in `.claude/settings.local.json`,
which is git-ignored.
