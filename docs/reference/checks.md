# Checks reference

What `make check` enforces and how to add a rule.

## Checks

Conventions that can be verified without judgement are enforced by `make check`
(`scripts/check.py`, Python standard library only). It needs no clone under `repos/`, runs in
seconds and prints one line per violation, saying what is wrong and what to do instead, then
the place where the convention is written. Run `python3 scripts/check.py --list` for the rules,
`--only a,b` to run some, `--root DIR` to check another workspace.

| Rule | What it enforces | Convention |
| ---- | ---------------- | ---------- |
| `manifest` | `repos.json` has only known keys, valid `products` slugs, and unique names and paths | [Manifest](workspace.md#manifest-reposjson) |
| `tracker` | `openspec/config.yaml` sets `x-tracker` to `linear`, `github` or `none` | [`docs/agents/issue-tracker.md`](../agents/issue-tracker.md) |
| `change-product` | when `repos.json` declares `products`, every change records one of them and its delta and main specs sit under it; without `products`, no change records one and specs sit at `<capability>/spec.md`; no Linear project or GitHub parent issue is shared between changes | [`docs/agents/openspec.md`](../agents/openspec.md), "Products and trackers" |
| `mcp-parity` | every MCP server is declared, with the same url, in `.mcp.json`, `.codex/config.toml` and `opencode.json` | [MCP servers](workspace.md#mcp-servers) |
| `skill-exposure` | each skill has valid frontmatter and is visible to Claude Code; none was written by the OpenSpec CLI; no broken links; `skills-lock.json` matches | [`docs/agents/workspace-changes.md`](../agents/workspace-changes.md), "Custom skills" |
| `tracked-secrets` | git tracks no env file, nothing under `env/` except placeholders, nothing under the clones directory | `env/README.md` |
| `openspec-validate` | `openspec validate --all --strict` passes; a workspace without `openspec/` has nothing to validate | [`docs/agents/openspec.md`](../agents/openspec.md) |
| `agents-map` | `AGENTS.md` exists and is at most 6000 bytes; every `docs/agents/*.md` is linked from it; every relative Markdown link in `AGENTS.md`, `README.md`, `docs/agents/*.md` and `docs/reference/*.md` resolves, anchors included | [AGENTS.md is a map](#agentsmd-is-a-map) |
| `guardrails` | `scripts/guard.py` is executable; `.claude/settings.json` and `.codex/hooks.json` have a `PreToolUse` hook on `Bash` that runs it with `--agent claude` / `--agent codex`; the OpenCode plugin's code (comments stripped) runs it with `--agent opencode` in a `tool.execute.before` hook | [Guardrails](guardrails.md#guardrails) |

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
