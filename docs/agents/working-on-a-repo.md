# Working on a repo (edit → commit → PR)

Read this before you edit, commit or open a PR in `repos/<name>` or in this workspace repo. Each
`repos/<name>` is its own git repository; the meta root never versions product code. For this
workspace repo itself, branch and open the PR from the root (steps 3 and 5 without `-C repos/<name>`),
and verify with `make check` and `make test` instead of `make repo-check`.

## Steps

1. Sync first: `scripts/init.sh --only <name>` (or `make sync ONLY=<name>`), to start from the
   latest default branch. To work on a subset of repos use `scripts/init.sh --only a,b` or
   `--product <slug>`; do not edit `repos.json` for that.
2. Read the repo's own instructions (`repos/<name>/AGENTS.md`, `CLAUDE.md`, `.claude/skills/`, and
   its generated `<repo>--instructions` skill) and follow them; they override anything in the
   meta repo. Prefer the repo's own skills over root-level ones when both exist.
3. Branch inside the repo; never commit to its default branch. In a meta worktree, repos start
   detached at `origin/<branch>`:
   `git -C repos/<name> checkout -b <type>/<short-slug>` (for example `feat/…`, `fix/…`, `chore/…`).
4. Make the change and run `make repo-check REPO=<name>`. When the manifest declares no `check` for
   the repo, find its command (its `AGENTS.md`, Makefile, package.json, pyproject.toml, CI), run
   it, and propose adding it as `check` in `repos.json`. Commit inside the repo, with a message
   per "Commits & PRs" below.
   When the user corrected you on a convention, run `create-rule` in that repo, on the same
   branch, in its own commit (see [conventions.md](conventions.md)).
5. Push, then open the PR from inside the repo:
   `git -C repos/<name> push -u origin HEAD`, then use the `create-pull-request` skill (title,
   body, `gh pr create`). Pushing to a branch that already has an open PR: use the skill again.
6. A change spanning several repos: one PR per repo, in the deployment order of the change's design
   (per phase when it ships in phases). Record each branch and PR in the change's `tasks.md`; the
   skill links the sibling PRs of the same phase.
7. Do not merge PRs, force-push, rewrite history or delete branches unless the user asks.

## Commits & PRs

Applies to every commit and PR, inside `repos/<name>` and in this meta repo.

- Commit messages and PR titles follow [Conventional Commits](https://www.conventionalcommits.org/):
  `<type>(<scope>): <description>`, with `feat`, `fix`, `chore`, `docs`, `refactor`, `test`, `ci`,
  `build` or `perf`; scope optional.
- PR title only: with an assigned task (a Linear issue id, for example `ABC-123`), the id is the
  **first word of the description**: `feat(login): ABC-123 add magic-link sign-in`. No task
  assigned: a plain description, `fix(api): handle empty payload`. Commits never carry the id.
- The PR body is a **briefing** for a teammate who has not opened the code. Build title and body
  with the `create-pull-request` skill.
