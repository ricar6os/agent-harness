# Issue tracker: Linear

Issues live in **Linear**; OpenSpec files in this repository are the source of truth for specs and tasks. Agents interact with Linear through the
**Linear MCP server** (`https://mcp.linear.app/mcp`), never by scraping the web UI and never
through the GitHub issue CLI.

## Availability

The server is declared once per client, always under the name `linear-server`:

`.mcp.json` (Claude Code):

```json
{
  "mcpServers": {
    "linear-server": { "type": "http", "url": "https://mcp.linear.app/mcp" }
  }
}
```

`.codex/config.toml` (Codex — the repository must be trusted for it to load):

```toml
[mcp_servers.linear-server]
url = "https://mcp.linear.app/mcp"
```

`opencode.json` (opencode):

```json
{
  "mcp": {
    "linear-server": { "type": "remote", "url": "https://mcp.linear.app/mcp", "enabled": true }
  }
}
```

It is an authenticated HTTP MCP server: the first use in a new environment triggers an OAuth
approval. If no Linear tools are exposed in the current session, **stop and say so**. Do not
invent issue IDs, and do not silently fall back to `gh issue`.

## Conventions

- **Discover the tool names from the connected server** rather than hardcoding them. The server
  exposes operations to list/search issues, read a single issue, create and update issues, read
  and add comments, and list teams, projects, statuses and labels.
- **Issue IDs** are `<TEAM>-<number>` (e.g. `ABC-123`, `ABC-4418`). Always cite the ID when
  referring to a ticket, in chat and in written artifacts.
- **Read before writing.** Fetch the issue and its comments before proposing an edit.
- **Never** close, reassign, or change the status of an issue unless the user asks for it (the one exception is the In Progress write in `openspec/config.yaml`).
- Multi-line bodies are Markdown. Keep Linear's own conventions (checklists, `ABC-123` mentions).

## Products, projects, epics and tasks

The rules (one product and one Linear project per change, Epics, tasks, dependencies, the one
status the agent writes) are written in `openspec/config.yaml`; the sync procedure is the
`openspec-linear-sync` skill. What is specific to Linear conventions:

- **Project label**: exactly one, under the group `Product`, matching the OpenSpec product.
  Product labels classify projects; issue labels classify Epics.
- **Epic**: an issue labelled `Epic`. **Task**: a child issue of its Epic, in the same project;
  its id is used in PR titles. There is no Story layer.

## Relation to this workspace

GitHub Issues are **not** used. GitHub holds code and pull requests only. A task's Linear issue ID
goes in the PR title, never in commits: see "Commits & PRs" in [working-on-a-repo.md](working-on-a-repo.md).

Each repo under `repos/` is a separate GitHub repository but they share the same Linear
workspace, so a single Linear issue can span several repos. For those, create an OpenSpec change
under `openspec/changes/` and link it from every PR.
