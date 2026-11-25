# Meta workspace

This repository holds no product code. It gives AI agents one entry point with visibility across every repository of the organization, and it holds the specs of work that spans several of them. `docs/reference/workspace.md` describes the layout: the `repos.json` manifest, `scripts/`, the clones in `repos/<name>/`, the secrets in `env/`, `openspec/` and `.agents/skills/`.

## Language

Write everything in this repository in English: code, comments, commits, scripts, skills, specs and docs. Reply to the user in their language.

## Hard rules

- When `repos/` is empty or incomplete, run `make sync` before working.
- Secrets live in `env/<name>/` of the main checkout, which every worktree shares (`scripts/init.sh` symlinks them). Keep them out of every commit, here and in the repos, and out of the conversation.
- Each `repos/<name>` is its own git repository: commit product code there. The root versions the manifest, the scripts, the specs and the skills.
- Work on a branch. A default branch changes only through a pull request.
- Ask first before removing entries from `repos.json`, merging PRs, force-pushing, rewriting history, deleting branches or touching production infrastructure.
- When a hook (`scripts/guard.py`) blocks a call, stop and ask the user. `scripts/guard.py --explain '<cmd>'` says why it blocked. The exception: when it asks you to read a repo's instructions before an edit, read them and repeat the edit.
- Run `make check` before committing here, and fix what it reports.
- When the user corrects you on a convention, also make it a rule where the convention lives ([conventions](docs/agents/conventions.md)). Start `deterministify` only when the user asks.

## Instruction precedence

When instructions conflict, the first of these wins:

1. Explicit user instructions
2. The `AGENTS.md` of the repository being edited (`repos/<name>/AGENTS.md`)
3. That repository's own skills
4. This file
5. The skills of this workspace

## Always

- Commits and PR titles follow Conventional Commits: `type(scope): description`.
- Work that spans several repos starts as an OpenSpec change (`openspec-propose`). Its `plan.md` splits the work into phases, `openspec-apply-change` implements one phase per run, and each phase gets one PR per repo.
- Issues live in the tracker that `x-tracker` sets in `openspec/config.yaml`: `linear`, `github` or `none` (then `plan.md` is the only tracking). Use only that one.

## Map

Read only what the task needs.

| About to | Read |
| -------- | ---- |
| Edit, commit or open a PR in `repos/<name>` or in this repo | [working-on-a-repo](docs/agents/working-on-a-repo.md); skill `create-pull-request` for title and body |
| Change this repo: skills, scripts, manifest, instructions, the OpenSpec schema or CLI version | [workspace-changes](docs/agents/workspace-changes.md) |
| Explore, propose, apply or archive an OpenSpec change | [openspec](docs/agents/openspec.md), then the `openspec-*` skill of that step |
| Write baseline specs from code | skill `openspec-create-spec-from-code` (user-invoked) |
| Read or write issues | [issue-tracker](docs/agents/issue-tracker.md) |
| Turn a correction into a rule | [conventions](docs/agents/conventions.md); skill `create-rule` (in a repo) |
| Clone or update repos | skill `sync-repos` |
