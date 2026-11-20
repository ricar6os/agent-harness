# Changing this workspace

Read this before you change the meta repo itself (not `repos/<name>`): skills, scripts,
manifest, OpenSpec files, instructions. For product code see [working-on-a-repo.md](working-on-a-repo.md).

## What agents may change

Yes, allowed:

- **Cloned repos (`repos/<name>`)**: edit code, run tests, branch, commit, push, open PRs per repo.
- **This meta repo**: add or edit skills in `.agents/skills/`, create OpenSpec changes
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

Skills live in `.agents/skills/<name>/`: a `SKILL.md` whose frontmatter `name` equals the
directory, and an `agents/openai.yaml` with the name and prompt Codex shows for it. A skill
vendored from another repository is pinned in `skills-lock.json`; change it upstream, not here.
After adding a skill, expose it to Claude Code:

- A skill with only a `SKILL.md`:
  `mkdir -p .claude/skills/<name> && ln -s ../../../.agents/skills/<name>/SKILL.md .claude/skills/<name>/SKILL.md`
- A skill with `references/`: symlink the whole directory instead. The loader reports the base
  directory as the `.claude/skills/<name>` path, so relative references must exist there:
  `ln -s ../../.agents/skills/<name> .claude/skills/<name>`

## The OpenSpec skills and schema

The `openspec-*` skills and `openspec/schemas/spec-plan/` are this workspace's own, and
harness-owned: change them in the harness repository. Keep both agnostic of where repos live;
that goes in the `context:` of `openspec/config.yaml`. After editing the schema run
`openspec schema validate spec-plan` and `make test`: `tests/test_openspec.py` writes a change
from the templates and takes it through validation and archive.

Run `openspec init` or `openspec update` nowhere here: they write the CLI's generic skills over
ours, and the `skill-exposure` rule reports a skill the CLI wrote.

## Upgrading OpenSpec

`openspec/cli-version` holds the version CI installs. Locally, that version or a newer one of
the same major runs the checks. To upgrade: write the new version in the file, install it, and
run `make check` and `make test`. `tests/test_openspec.py` fails when a command the skills use
changed; adapt the skill that uses it ([openspec.md](openspec.md) lists them).

## Local files

Local `.env` and secret files live in `env/<name>/` of the main checkout, never in `repos/<name>/`
directly and never committed; `scripts/init.sh` symlinks them (see `env/README.md`). Never write
secrets into files versioned here, and never paste them into the conversation.
