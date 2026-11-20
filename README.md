# agent-harness

This repository is the upstream harness for meta workspaces: a repo with no product code that groups an
organization's repositories so AI agents get organization-wide context, cross-repo
[OpenSpec](https://github.com/Fission-AI/OpenSpec) specs and shared skills. Each meta is a
copy that keeps this repository's history, so harness updates arrive with a merge.

## Create a meta repo

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
4. `make doctor && make sync && make check`, then open the meta's first PR.
5. Pick the issue tracker with `x-tracker` at the top of `openspec/config.yaml`: `linear`, `github` or `none` (see "Issue tracker" below). With Linear, the team is resolved with the user at the first sync.

## Bring harness updates into a meta

```bash
git fetch harness
git checkout -b chore/harness-update origin/main
git merge harness/main
make check && make test
```

Conflicts can only come from instance-owned files (below) or from harness files the meta
changed on purpose, such as the `x-tracker` line of step 5: keep the meta's side for those.
Open the result as a PR in the meta.

## Harness files and your files

| Harness-owned (kept identical across every meta) | Instance-owned |
| ------------------------------------------------ | -------------- |
| `scripts/`, `Makefile`, `tests/` | `repos.json` |
| `.agents/skills/` (custom and vendored) | `docs/conventions/` (workspace conventions no rule can check) |
| `.claude/`, `.opencode/`, `.github/workflows/` | `openspec/changes/`, `openspec/specs/` |
| `docs/agents/`, `openspec/schemas/`, `openspec/cli-version` | The `x-tracker` line and your own additions to the `context:` of `openspec/config.yaml` |
| MCP config files (`.mcp.json`, `.codex/config.toml`, `opencode.json`) | `env/` |
| Guardrail wiring (`.claude/settings.json`, `.codex/hooks.json`, `.opencode/plugins/guard.js`) | |

Improve harness files here first, with a PR to this repository, then merge them into each meta.

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
tests/                   tests of the checker, the guardrails, the scripts and the OpenSpec CLI contract (`make test`)
.github/workflows/check.yml  runs the checks and the tests on every pull request
repos/<name>/            org repos (git-ignored; each one is its own git repository)
env/<name>/              local .env/secret files symlinked into repos/<name>/ by init.sh (git-ignored)
openspec/                OpenSpec: schemas/spec-plan/ (our workflow), config.yaml, cli-version (the CLI version CI installs), changes/ (in-flight work), specs/ (main specs)
.agents/skills/          root-level skills, the canonical location (Codex/ChatGPT + Claude Code)
.claude/skills/          Claude Code skills: symlinks to .agents/skills/ for every skill
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
make check                   # check the workspace conventions (see "Checks")
make test                    # run the tests (checker, guardrails, scripts, OpenSpec CLI contract)
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
(`gh auth status`) and, for the spec workflow, the `openspec` CLI at the version in `openspec/cli-version` or a newer one of the same major (`npm i -g "@fission-ai/openspec@$(cat openspec/cli-version)"`).

## Checks

Conventions that can be verified without judgement are enforced by `make check`
(`scripts/check.py`, Python standard library only). It needs no clone under `repos/`, runs in
seconds and prints one line per violation, saying what is wrong and what to do instead, then
the place where the convention is written. Run `python3 scripts/check.py --list` for the rules,
`--only a,b` to run some, `--root DIR` to check another workspace.

| Rule | What it enforces | Convention |
| ---- | ---------------- | ---------- |
| `manifest` | `repos.json` has only known keys, valid `products` slugs, and unique names and paths | [Manifest](#manifest-reposjson) |
| `tracker` | `openspec/config.yaml` sets `x-tracker` to `linear`, `github` or `none` | [`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md) |
| `change-product` | when `repos.json` declares `products`, every change records one of them and its delta and main specs sit under it; without `products`, no change records one and specs sit at `<capability>/spec.md`; no Linear project is shared between changes | [`docs/agents/openspec.md`](docs/agents/openspec.md), "Products and trackers" |
| `mcp-parity` | every MCP server is declared, with the same url, in `.mcp.json`, `.codex/config.toml` and `opencode.json` | [MCP servers](#mcp-servers) |
| `skill-exposure` | each skill has valid frontmatter and is visible to Claude Code; none was written by the OpenSpec CLI; no broken links; `skills-lock.json` matches | [`docs/agents/workspace-changes.md`](docs/agents/workspace-changes.md), "Custom skills" |
| `tracked-secrets` | git tracks no env file, nothing under `env/` except placeholders, nothing under the clones directory | `env/README.md` |
| `openspec-validate` | `openspec validate --all --strict` passes; a workspace without `openspec/` has nothing to validate | [`docs/agents/openspec.md`](docs/agents/openspec.md) |
| `agents-map` | `AGENTS.md` exists and is at most 6000 bytes; every `docs/agents/*.md` is linked from it; every relative Markdown link in `AGENTS.md` and `docs/agents/*.md` resolves | [AGENTS.md is a map](#agentsmd-is-a-map) |
| `guardrails` | `scripts/guard.py` is executable; `.claude/settings.json` and `.codex/hooks.json` have a `PreToolUse` hook on `Bash` that runs it with `--agent claude` / `--agent codex`; the OpenCode plugin's code (comments stripped) runs it with `--agent opencode` in a `tool.execute.before` hook | [Guardrails](#guardrails) |

A rule skips, and says so, when it cannot run: the `openspec` CLI is missing, older than
`openspec/cli-version` or of another major version (`openspec-validate`), the directory is not a
git work tree, or (`mcp-parity`, on Python 3.9 and 3.10 only) `.codex/config.toml` uses TOML the
built-in fallback parser does not implement and needs Python 3.11+. With `--require-tools` those
cases are violations instead; CI uses it, so a skip never hides a failure there.

CI (`.github/workflows/check.yml`) runs `scripts/check.py --require-tools` and the tests on
every pull request and on pushes to `main`.

### AGENTS.md is a map

Every agent loads `AGENTS.md` at the start of every session, so it holds only the rules that must
hold in every session and a map saying which file to read for which task. It is capped at 6000
bytes (rule `agents-map`). Detail lives in `docs/agents/`, one short file per topic, and each
file is linked from `AGENTS.md` with a line saying when to read it. Relative links in these files
must resolve. A rule stated in full where it is used (the schema for what a change contains,
a skill for its task) is pointed to, not copied.

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

The OpenCode plugin is a plain `export default { id, setup }` object that imports only Node
built-ins, so a fresh clone needs no package install. It was verified with OpenCode 2.3.2 on
macOS; other versions were not tried.

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

## Three layers

The harness keeps apart what every workspace needs, where the code lives and how work is
planned, so each part can change without the others:

| Layer | What | Files |
| ----- | ---- | ----- |
| Core | Agent instructions as a map, guardrails, checks, MCP parity, secrets, PR and rule skills | `AGENTS.md`, `docs/agents/`, `scripts/`, `.agents/skills/` |
| Topology | Where the code lives: one repo, this meta with `repos.json`, or an OpenSpec store (beta, not wired yet) | `repos.json`, `scripts/init.sh`, the `context:` of `openspec/config.yaml` |
| Method | How a change is specified, planned and implemented | `openspec/schemas/spec-plan/`, the `openspec-*` skills |

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

The workspace depends on OpenSpec for its file layout (`openspec/specs/`, `openspec/changes/`, delta
specs) and for six CLI commands: `new change`, `status`, `instructions`, `list`, `validate` and
`archive`. The four `openspec-*` workflow skills are our own, short and written for this schema;
the CLI's generated skills are not installed, because they are written for the default schema
and contradict ours (they list `proposal.md`, `design.md` and `tasks.md`, and their apply runs
every task instead of one phase). `tests/test_openspec.py` runs each command against the schema
and its templates, so a CLI upgrade that breaks one fails `make test`.
[`docs/agents/openspec.md`](docs/agents/openspec.md) lists what each command is used for.

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
[`openspec-create-spec-from-code`](.agents/skills/openspec-create-spec-from-code/SKILL.md)
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

With a tracker, the [`openspec-tracker-sync` skill](.agents/skills/openspec-tracker-sync/SKILL.md)
runs after `plan.md` is written or edited, and before archive. It writes the issue reference at
the end of the phase heading (`### Phase 1: Durable order ids [ABC-123]`) and records the
container in `.openspec.yaml` (`x-linear-project` or `x-github-issue`). When apply starts a
phase, the agent marks its issue started (In Progress in Linear, assigned to you in GitHub);
that is the only progress it writes, and you move or close issues from there. The skills read
`x-tracker` and behave the same for every tracker, so switching is that one line; `make
check` (rule `tracker`) accepts only the three values. Details per tracker are in
[`docs/agents/issue-tracker.md`](docs/agents/issue-tracker.md). Linear access uses the
`linear-server` MCP server (see "MCP servers" below); GitHub uses `gh`.

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

## Skills

- **Root skills** live in `.agents/skills/` (canonical), each with a symlink in `.claude/skills/`. Two kinds:
  - _Custom_: written here. `openspec-explore`, `openspec-propose`, `openspec-apply-change` and
    `openspec-archive-change` are the workflow; `openspec-tracker-sync` mirrors phases to the
    tracker; `sync-repos` clones and updates the repos; `unslop` edits writing.
    `create-pull-request` and `openspec-create-spec-from-code` are adapted from
    CodelyTV/agent-harness (MIT): the first writes the title and body of a PR with evidence,
    deploy steps, rollback and links between the PRs of a phase; the second writes the baseline
    main specs of existing behaviour from the code, and only the user starts it.
  - _Vendored_ (`create-rule`, `deterministify` from
    [CodelyTV/agent-harness](https://github.com/CodelyTV/agent-harness)): upstream skills pinned
    in `skills-lock.json`, never edited here.
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
