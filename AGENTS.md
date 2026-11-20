# meta — multi-repo workspace

Repo holds no product code. Entry point for AI agents w/ visibility across every org repo, and for specs spanning several repos. Layout is in `README.md`: `repos.json` manifest, `scripts/`, `repos/<name>/` clones, `env/` secrets, `openspec/`, `.agents/skills/`.

## Language

**Everything here written in English**: code, comments, commits, scripts, skills, specs, docs. Reply to the user in their language, never write Spanish (or other) into files here.

## Hard rules

- `repos/` empty or incomplete → `make sync` before working.
- Secrets live in `env/<name>/` of the main checkout only (shared by every worktree; `scripts/init.sh` symlinks them): never committed, here or in any repo, never in the conversation.
- Each `repos/<name>` is its own git repo: product code is committed there, never from the root. Root versions manifest, scripts, specs, skills.
- Never commit to a default branch.
- Ask first before: removing entries from `repos.json`, merging PRs, force-pushing, rewriting history, deleting branches, anything touching prod infra.
- Hook block (`scripts/guard.py`) → stop and ask; never find another route. `scripts/guard.py --explain '<cmd>'` says why.
- `make check` before committing here; fix what it reports, never bypass.
- Never hand-edit generated `openspec-*` skills: run `make openspec`.
- User corrects a convention → make it a rule where it lives, not only a fix (`docs/agents/conventions.md`). Start `deterministify` only when the user asks.
- Repo instructions (`repos/<name>/AGENTS.md`) are more specific than this file.

## Instruction precedence

When instructions conflict, use this precedence:

1. Explicit user instructions
2. Repository-local AGENTS.md
3. Repository-local relevant skills
4. Meta-repository AGENTS.md
5. Meta-repository skills

Repository-specific instructions override organization defaults. Prefer a repo's own skills over root-level ones.

## Always

- OpenSpec: when `repos.json` declares `products`, a change has one product (`x-product`). Resolve and announce the product before any OpenSpec operation; never infer it.
- Commits and PR titles: Conventional Commits, `type(scope): description`; PR title with a task id: `feat(x): ABC-123 add y`; commits never carry the id.
- A change spanning several repos starts as an OpenSpec change (`/openspec-propose`): each phase of its `plan.md` names its repos in deployment order; apply implements one phase per run; one PR per repo and phase.
- Issues live in the tracker set by `x-tracker` in `openspec/config.yaml`: `linear`, `github` or `none` (only `plan.md`). Never use another one.

## Map

Read only what the task needs.

| About to | Read |
| -------- | ---- |
| Edit, commit or open a PR in `repos/<name>` or in this repo | [working-on-a-repo](docs/agents/working-on-a-repo.md); skill `create-pull-request` for title and body |
| Change this repo: skills, scripts, manifest, instructions; add a repo to the manifest; upgrade the OpenSpec CLI | [workspace-changes](docs/agents/workspace-changes.md) |
| Propose, apply or archive an OpenSpec change | [openspec](docs/agents/openspec.md); skill `openspec-tracker-sync` after `plan.md` changes |
| Write baseline specs from code | skill `openspec-create-spec-from-code` (user-invoked) |
| Read or write issues | [issue-tracker](docs/agents/issue-tracker.md) |
| Turn a correction into a rule | [conventions](docs/agents/conventions.md); skill `create-rule` (in a repo) |
| Clone or update repos | skill `sync-repos` |
