---
name: openspec-linear-sync
description: Sync an OpenSpec change to its own Linear project, labelled by Product, with an Epic per objective-based task group and an issue per task; the only status write is moving an issue to In Progress when apply starts its task. Use after tasks.md is created or updated, or before archiving.
---

# openspec-linear-sync

`tasks.md` is the source of truth for mirrored work. One OpenSpec change belongs to one
OpenSpec product and corresponds exclusively to one Linear project. Resolve the product
as `docs/agents/openspec.md` describes before synchronizing; split cross-product work into separate changes.

## Binding and mapping

Keep the product and the Linear destination separate in `.openspec.yaml`:

```yaml
x-product: shop
x-linear-project:
  id: <actual Linear project UUID>
  url: <actual Linear project URL>
x-linear-sync-version: 2
```

`x-product` is the product slug used by `repos.json` and spec paths. The Linear project carries
exactly one project label in the group `Product`; the label name normalized to kebab-case
must match that slug. This is a project label, not an issue label or a Linear team.
`x-linear-sync-version: 2` identifies the mapping below; write it after checking legacy state.

| OpenSpec | Linear | Local reference |
| --- | --- | --- |
| Change | One dedicated project, with a proposal summary and link to the change | `x-linear-project.id` and `.url` in `.openspec.yaml` |
| Numbered group heading `## N. <objective>` | Issue labelled `Epic`, describing the common objective and completion criteria | Issue id suffix on the heading |
| Numbered checkbox `- [ ] N.M <task>` | Individual child issue of the group's Epic, explicitly assigned to the same project and selected team | Issue id suffix on the task line |
| `Depends on:` line of a group or task | "Blocked by" relation from that item's issue to each referenced item's issue | The local numbers on the line; see "Dependencies" |

Example after synchronization (ids are illustrative):

```markdown
## 1. Give orders durable identities [ABC-123]

Objective: every order has an identifier that survives re-imports.

- [ ] 1.1 Add persistent order identifiers; verify uniqueness [ABC-124] <!-- in-progress -->
- [x] 1.2 Expose identifiers in the API; verify response contract [ABC-125]
  - Depends on: 1.1

## 2. Release [ABC-126]

Objective: identifiers reach production without breaking consumers.

Depends on: 1

- [ ] 2.1 Deploy and confirm the backfill; verify counts per environment [ABC-127]
  - Depends on: 1
```

Each task issue describes the task, acceptance criteria and relevant spec/design links.
Every creation payload also includes a source link to `tasks.md` and an exact identity line:
`OpenSpec source: <change>/group/<N>` for Epics, or
`OpenSpec source: <change>/task/<N.M>` for tasks. Use the change directory name and numbered
group/task identifier. Persist this line in Linear in the same call that creates the issue,
so recovery works even if writing the returned id to the local file fails. Keep it current
when renumbering an already-linked item, addressing that item by its recorded issue id.
Retain existing task labels.
There is no Story layer and no additional issue wrapping the whole change. Task issue ids
are the ids used in PR titles. Only numbered task checkboxes are work items; nested
acceptance checklists stay in the task description. Groups must state a common objective;
if existing groups mix unrelated objectives, resolve their grouping before publishing.

## Dependencies

`tasks.md` declares what each item waits for, and the sync mirrors it, so Linear shows what
is blocked and by what. Review dependencies on every sync, including a first sync of a file
that declares none: a file with several groups and no `Depends on:` line is a finding to
raise with the user, not a fact to assume.

Notation, using the local numbers and never Linear ids:

- A task declares its dependencies in a nested bullet directly under its checkbox line:
  `  - Depends on: 2.1, 3`. `N.M` refers to a task, `N` to a whole group.
- A group declares its dependencies in a `Depends on: 1, 2` paragraph after its objective.
  Group references only.
- No line means the item can start at once.

What counts as a dependency: the item cannot be completed, merged or verified until the other
is done. Declare direct dependencies only and leave out what follows transitively. Order in
the file and "would be nicer after" are not dependencies.

Across repos, a task whose code calls a field, filter, endpoint or column that another task
introduces depends on that task, even when it can be written and unit-tested against a mock.
Done means merged, and a merge to a default branch usually deploys to a shared environment, so
a consumer merged before its provider breaks that environment. Check each repo's deploy
workflow instead of assuming. A task that reaches production by a manual deploy depends on
the task that deploys its provider there. Only work with no runtime use of the new contract,
such as adding types or tolerating a missing value, is free of the provider.

Declare a group dependency only when no
task of the group can start before the other group is complete; when only some tasks wait,
declare it on those tasks. Never derive group dependencies from task dependencies: the task
graph can be acyclic while the derived group graph is not.

Validate before any external write: every reference resolves to an existing group or task,
no item depends on itself or on its own group, and neither the task graph nor the group graph
contains a cycle. `make check` (rule `task-dependencies`) performs this validation. When the file fails, stop and fix `tasks.md` with the user.

Mirror each dependency as a "blocked by" relation from the dependent issue to the issue of
each referenced task, or to the Epic of each referenced group. Relations are a managed field:
read the current ones, add those missing, and remove a relation only when both issues belong
to this change and the local line no longer declares it. Leave relations to issues outside
the change, and relations of other kinds, as they are. Keep `Depends on:` lines out of issue
descriptions; the relation carries them. After renumbering, rewrite the affected lines in the
same edit so every reference still resolves.

## Synchronize

1. **Read and validate local scope.** Read `.openspec.yaml`, `proposal.md`, `tasks.md` and
   relevant specs/design. Collect group and task ids, checkbox state, active markers and
   `Depends on:` lines, and validate them as "Dependencies" requires.
   Confirm all capabilities and affected repos stay within the selected product (shared
   repos only within that scope). If ids repeat, tasks lack groups, or old annotations are
   present, resolve them before external writes. Apply the legacy rules below when needed.
2. **Discover Linear capabilities.** Use the connected Linear MCP tools as described in
   `docs/agents/issue-tracker.md`. Discover project, project-label/group, issue, team, status
   and issue-label operations. Product grouping must be supported by the actual tools;
   do not substitute an issue label. If a required operation is unavailable, report the
   specific missing capability and retain the local artifacts for a later sync.
3. **Resolve the destination.** Use the user's selected project or fetch the recorded id.
   If they conflict, ask before moving any work. With neither, list candidate projects and
   ask which to use or whether to create a dedicated one. Create only when the user requests
   it and the team is known. Derive a new project's name from the proposal's human title or
   the change name, respecting any name supplied by the user. For a multi-team project,
   resolve the issue team with the user. Check other local changes, including archived ones,
   and the destination's existing OpenSpec links: reject a project bound to another change.
   A missing/deleted recorded project needs reconciliation, not automatic replacement.
4. **Ensure Product classification and binding.** Find the project-label group `Product`
   and the child label matching `x-product`. Reuse existing ids; create the missing group or
   child label as part of the requested sync when supported. If the selected project has a
   different Product label or multiple Product labels, ask before reclassifying it. Add the
   matching label while preserving labels outside Product. Keep the project's description
   and other settings; add/update only the OpenSpec summary and source link. Record the real
   project id and URL immediately. Done when the project is exclusively bound to this change
   and classified under its one product. Do not change the Linear project's status.
5. **Read existing work before updating it.** Fetch referenced issues and comments, and
   compare project, team, parent, labels, description, relations and state. A missing id or an issue
   belonging elsewhere requires reconciliation before replacement or movement. Check state
   as read-only input: a sync reports state differences and never writes them (see "State").
6. **Sync Epics, then tasks.** Reuse recorded ids. For unannotated items, search the project's
   issues (including closed issues) for the exact `OpenSpec source:` identity line
   before creating anything; recover a unique match after an interrupted run. A title
   match alone is not identity: ask about ambiguous candidates. Create each missing Epic,
   record its id immediately, then create its task issues with explicit project and parent
   ids and record each returned id immediately. Create issues without a status so the team's
   default applies. Preserve ids through title edits/reordering;
   never replace a task's id with its Epic's. Update only changed managed fields, preserving
   unrelated issue content. Repeated syncs with no drift perform no writes.
7. **Sync dependencies.** Once every group and task has an issue id, mirror the `Depends on:`
   lines as "blocked by" relations, as "Dependencies" describes. This runs after step 6
   because a relation needs both issues to exist. Read back at least the relations you wrote.
8. **Report verified results.** Read back created/changed records. Report the product, Linear
   project link, Epics and individual tasks created/updated/unchanged, relations added or
   removed, items that declare no dependency in a multi-group file, state differences
   between the file and Linear (left unwritten), and unresolved items.
   Never report completion if project classification, binding or any required issue failed.
   Removed local tasks/groups are reported as orphans; do not delete their Linear issues.

## State

The agent writes one status, In Progress, at the moment apply starts a task. From there the
developer moves the cards in Linear. Nothing else changes a status, including checking a
task off, completing a whole group, a sync, an archive, or a request to mark an issue Done.
The agent answers such a request by pointing the user to Linear.

When apply adds `<!-- in-progress -->` to a task that has an issue id:

- Fetch the task issue. If its status type is backlog or unstarted (Backlog, Todo), set it
  to the selected team's In Progress status, using that team's actual status id.
- Apply the same rule to the task's parent Epic, so an Epic with started work is not left
  in Todo.
- If the issue is already In Progress, further along (In Review, Done) or cancelled, leave
  it as it is and mention it in the report. Never move an issue backwards.
- A task without an issue id gets the local marker only. Do not run a sync to obtain one.

The checkbox and the marker record local progress in `tasks.md`; sync keeps the marker and
the issue id annotation out of issue descriptions. A sync never writes a status, not even In
Progress for a task that already carries the marker. When the file and Linear disagree, list
the differences in the report and leave both sides unchanged. Never mark local checkboxes
from remote state.

## Legacy bindings

A change that still uses `product`, `linear_project` or `linear_sync_version` is migrated by
renaming the keys in place to `x-product`, `x-linear-project` and `x-linear-sync-version`,
values unchanged, before any sync. OpenSpec 2 rejects unknown keys in strict validation.

A change with only `x-product: shop` and no issue annotations can retain that product and
resolve a dedicated Linear project on its first sync. Do not interpret `shop` as a Linear
project name or invent an id.

A `Linear epic:` line, existing issue annotations without `x-linear-sync-version: 2`, or
headings referring to Story issues indicate a legacy mapping. Read the actual linked records
and present the mapping to the user before converting it. Existing heading ids may refer to
Stories and cannot silently become Epics; the old change-level Epic cannot become a project.
Resolve the dedicated destination and each issue's reuse/move/label/parent change explicitly,
then annotate each individual task and record version 2. Preserve legacy references until
that mapping is reconciled. A normal sync does not bulk-migrate, delete or close legacy work.
