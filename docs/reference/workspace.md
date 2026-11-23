# Meta workspace reference

Layout, commands, local files and the manifest of a meta workspace.

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
branch before committing (step 3 of [`docs/agents/working-on-a-repo.md`](../agents/working-on-a-repo.md)). Removing the meta
worktree leaves a stale entry in the main clone, which the next sync prunes. Set
`META_REPO_WORKTREES=0` to clone instead.

Requirements: `git`, `jq`, `python3` (3.9 or newer, standard library only; 3.11 or newer for the `mcp-parity` rule), SSH access to GitHub
(`gh auth status`) and, for the spec workflow, the `openspec` CLI at the version in `openspec/cli-version` or a newer one of the same major (`npm i -g "@fission-ai/openspec@$(cat openspec/cli-version)"`).

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

## Working on repos

AI agents can edit code, commit and open PRs in every cloned repo. Each `repos/<name>` is an
independent git repository: branch, commit and `gh pr create` from inside it, one PR per repo.
The full workflow is described in [`docs/agents/working-on-a-repo.md`](../agents/working-on-a-repo.md).

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
