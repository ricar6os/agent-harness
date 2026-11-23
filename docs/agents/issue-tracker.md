# Issue tracker

Read this before you read or write issues. The tracker is set by one line at the top of
`openspec/config.yaml` (rule `tracker` of `make check`):

| `x-tracker` | Issues live in | Tools |
| --- | --- | --- |
| `linear` | Linear: one project per change, one issue per phase | the `linear-server` MCP server |
| `github` | GitHub Issues of the workspace repo: one parent issue per change, one sub-issue per phase | the `gh` CLI |
| `none` | nowhere: the checkboxes of each change's `plan.md` are the tracking | none |

OpenSpec files are the source of truth for specs and plans; the tracker mirrors phases. The sync
procedure and the one progress write the agent makes are in the `openspec-tracker-sync` skill,
with one reference per tracker. Use only the configured tracker: never fall back to another one,
and with `none` create no issues anywhere.

## Every tracker

- **Read before writing.** Fetch the issue and its comments before proposing an edit.
- **Cite the reference** (`ABC-123`, `owner/repo#13`) when referring to an issue, in chat and in
  written artifacts. Never invent one.
- **Never** close, reassign or change the status of an issue unless the user asks, except the
  one write apply makes when it starts a phase (In Progress in Linear, assignment in GitHub).
- **PRs**: one per repo and phase; how a PR names its phase's issue is in
  [working-on-a-repo.md](working-on-a-repo.md), "Commits & PRs".

## Linear

The `linear-server` MCP server (`https://mcp.linear.app/mcp`) is declared under that name in
`.mcp.json`, `.codex/config.toml` and `opencode.json` (rule `mcp-parity`). It is an
authenticated HTTP server: the first use in a new environment asks for an OAuth approval. If no
Linear tools are exposed in the session, stop and say so. Discover tool names from the
connected server rather than hardcoding them. Issue ids are `<TEAM>-<number>`.

## GitHub

`gh` must be authenticated (`make doctor` checks it). Issues are opened in the workspace repo,
the one that holds `openspec/`, never in `repos/<name>`, because a phase can span several repos.

## Switching tracker

Change `x-tracker` and run `make check`. A workspace that does not use Linear can remove the
`linear-server` entries from the three MCP files (all three, or `mcp-parity` fails). Changes
already bound to the old tracker keep their references; sync them again only if the user asks.
