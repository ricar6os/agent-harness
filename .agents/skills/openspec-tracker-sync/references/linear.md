# Linear

Tools: the `linear-server` MCP server. Discover its tool names from the connected server.
Conventions: [docs/agents/issue-tracker.md](../../../../docs/agents/issue-tracker.md).

## Mapping

| OpenSpec | Linear | Local reference |
| --- | --- | --- |
| Change | One dedicated project; its description holds the plan's Goal and a link to the change | `x-linear-project` in `.openspec.yaml` |
| `### Phase N: <slice>` | One issue in that project: the phase's description, repos and tasks as a checklist, a link to `plan.md` | `[ABC-123]` at the end of the heading |
| `x-product` (when the change has one) | Exactly one project label in the group `Product`, matching the slug | none |

```yaml
x-linear-project:
  id: <Linear project UUID>
  url: <Linear project URL>
x-linear-sync-version: 3
```

## Specifics

- **Creating the project**: on the user's yes and once the team is known, named after the plan
  title. A project's status stays as the user set it.
- **Product label**: only when the change has `x-product`. Ensure the `Product` group and the
  matching label exist and that the project carries that one label. If it carries a different
  Product label, ask before changing it. Keep labels outside the group.
- **Creating an issue**: in the project and team, without a status, so the team default applies.
- **Started**: when apply starts a phase, fetch its issue; if its status type is backlog or
  unstarted (Backlog, Todo), move it to the team's In Progress status. If it is already started,
  done or cancelled, leave it and mention it.
- **Finished**: status type completed (Done).
- **PR titles**: the phase's issue id is the first word of the description, in every repo of
  that phase: `feat(login): ABC-123 add magic-link sign-in`.

## Older changes

A change with `tasks.md` and `x-linear-sync-version: 2` uses the old Epic and task mapping. Do
not sync it: tell the user, and leave it until it is archived or they migrate it by hand.
