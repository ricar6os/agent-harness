# Changing this workspace

Read this before you change the meta repo itself (not `repos/<name>`): skills, scripts,
manifest, OpenSpec files, instructions. For product code see [working-on-a-repo.md](working-on-a-repo.md).

## What agents may change

Yes, allowed:

- **Cloned repos (`repos/<name>`)**: edit code, run tests, branch, commit, push, open PRs per repo.
- **This meta repo**: add or edit custom skills in `.agents/skills/`, create OpenSpec changes
  under `openspec/changes/`, improve `scripts/`, update `AGENTS.md` and `README.md`, add repos to
  `repos.json`.

`AGENTS.md` is a map capped at 6000 bytes (rule `agents-map`): put detail in `docs/agents/` and
link it from the map. To open a PR in this repo follow [working-on-a-repo.md](working-on-a-repo.md); the
checks are `make check` and `make test`. Run `make check` before committing here: `python3 scripts/check.py --list` names every rule it enforces, and
[`README.md`](../../README.md#checks) "Checks" says what each one verifies. Fix what it
reports; never bypass it.

## Ask first

The ask-first list and the hook rule are in [`AGENTS.md`](../../AGENTS.md) "Hard rules".

## Adding a repo to the manifest

Add the entry to `repos.json` (format: [`README.md`](../../README.md#manifest-reposjson), "Manifest (`repos.json`)"), run `make sync ONLY=<name>`
to clone it, then `make check`.

## Custom skills

After adding a custom skill, expose it to Claude Code:

- A skill with only a `SKILL.md`:
  `mkdir -p .claude/skills/<name> && ln -s ../../../.agents/skills/<name>/SKILL.md .claude/skills/<name>/SKILL.md`
- A skill with `references/`: symlink the whole directory instead. The loader reports the base
  directory as the `.claude/skills/<name>` path, so relative references must exist there:
  `ln -s ../../.agents/skills/<name> .claude/skills/<name>`

## Generated files

Never hand-edit the generated `openspec-*` skills; run `make openspec`.

## The OpenSpec schema

`openspec/schemas/spec-plan/` is harness-owned: change it in the harness repository, keep it agnostic of
where repos live (that goes in the `context:` of `openspec/config.yaml`), and run
`openspec schema validate spec-plan` after editing it.

## Upgrading OpenSpec

To upgrade OpenSpec: write the new version in `openspec/cli-version`, install that version, run
`make openspec`, run `make check`, commit.

## Local files

Local `.env` and secret files live in `env/<name>/` of the main checkout, never in `repos/<name>/`
directly and never committed; `scripts/init.sh` symlinks them (see `env/README.md`). Never write
secrets into files versioned here, and never paste them into the conversation.
