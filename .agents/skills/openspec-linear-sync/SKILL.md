---
name: openspec-linear-sync
description: Sync an OpenSpec change to its own Linear project with one issue per phase of plan.md; the only status write is moving a phase's issue to In Progress when apply starts it. Use after plan.md is created or edited, or before archiving.
---

# openspec-linear-sync

`plan.md` is the source of truth. One change is one Linear project; each phase of `plan.md`
is one issue in it. Nothing else is mirrored: tasks stay checkboxes in the phase, specs stay
in the change.

## Binding and mapping

`.openspec.yaml` records the project with the real values Linear returns:

```yaml
x-linear-project:
  id: <Linear project UUID>
  url: <Linear project URL>
x-linear-sync-version: 3
```

| OpenSpec | Linear | Local reference |
| --- | --- | --- |
| Change | One dedicated project; its description holds the plan's Goal and a link to the change | `x-linear-project` in `.openspec.yaml` |
| `### Phase N: <slice>` | One issue in that project: the phase's description, repos and tasks as a checklist, a link to `plan.md` | Issue id at the end of the heading: `### Phase 1: Durable order ids [ABC-123]` |
| `x-product` (when the change has one) | Exactly one project label in the group `Product`, matching the slug | none |

Every issue carries the line `OpenSpec source: <change>/phase/<N>` from the call that creates
it, so an interrupted run can find it again. Phases run in file order; no "blocked by"
relations are written. The phase issue id is the one PR titles use, in every repo of that
phase.

## Synchronize

1. **Read local scope.** Read `.openspec.yaml` and `plan.md`. Collect each phase's number,
   title, recorded id and checkboxes.
2. **Check the Linear tools.** Use the connected `linear-server` MCP tools as
   [issue-tracker.md](../../../docs/agents/issue-tracker.md) says. If a required operation is
   missing, name it, stop and leave the local files for a later sync.
3. **Resolve the project.** Use the user's choice or the recorded id; if they conflict, ask.
   With neither, list candidate projects and ask which to use or whether to create one.
   Create only when the user asks and the team is known, named after the plan title. Reject a
   project already bound to another change, archived ones included. Record the id and url at
   once. Never change the project's status.
4. **Product label.** Only when the change has `x-product`: ensure the `Product` group and
   the matching label exist, and that the project carries that one label. If it carries a
   different Product label, ask before changing it. Keep labels outside the group.
5. **Sync phases.** For a phase with an id, fetch the issue and update only the managed
   fields that changed (title, description). For a phase without one, search the project,
   closed issues included, for its `OpenSpec source:` line; reuse a single match, ask about
   several. Otherwise create it without a status, so the team default applies, and write its
   id into the heading at once. Renumbered phases keep their ids; update the source line.
   An unchanged sync writes nothing.
6. **Report.** Read back what you wrote. Report the project link, the phases created, updated
   and unchanged, the phases whose status in Linear disagrees with the checkboxes (left as
   they are), and orphans: issues of the project whose phase no longer exists. Never delete
   or close an orphan.

## State

The agent writes one status, at one moment: when apply starts a phase whose heading has an
issue id, fetch the issue and, if it is in Backlog or Todo, move it to the team's In Progress
status. If it is already started, done or cancelled, leave it and mention it. Never move an
issue backwards, never write a status during a sync or an archive, and never mark local
checkboxes from Linear. When the user asks to mark an issue Done, point them to Linear.

## Older changes

A change with `tasks.md` and `x-linear-sync-version: 2` uses the old Epic and task mapping.
Do not sync it with this skill: tell the user, and leave it until it is archived or they ask
to migrate it by hand.
