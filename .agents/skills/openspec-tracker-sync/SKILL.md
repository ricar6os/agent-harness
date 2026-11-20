---
name: openspec-tracker-sync
description: Sync an OpenSpec change to the issue tracker set by x-tracker in openspec/config.yaml (Linear or GitHub), one issue per phase of plan.md; the only status write is marking a phase's issue started when apply starts it. Use after plan.md is created or edited, or before archiving. Does nothing when x-tracker is none.
---

# openspec-tracker-sync

`plan.md` is the source of truth. One change is one container in the tracker and each phase of
`plan.md` is one issue in it. Tasks stay checkboxes in the phase; specs stay in the change.

## 1. Pick the tracker

Read `x-tracker` at the top of `openspec/config.yaml`:

| Value | Container per change | Issue per phase | Read |
| --- | --- | --- | --- |
| `linear` | A Linear project | An issue in that project | [references/linear.md](references/linear.md) |
| `github` | A parent issue in the repo that holds the change | A sub-issue of it | [references/github.md](references/github.md) |
| `none` | nothing | nothing | stop: `plan.md` checkboxes are the only tracking |

Read only the reference of the configured tracker. If its tools are not available in this
session (MCP server not connected, `gh` not authenticated), name what is missing, stop, and leave
the local files for a later sync. Never fall back to the other tracker.

## 2. Rules for every tracker

- **Identity.** Every issue carries a line `OpenSpec source: <change>` (container) or
  `OpenSpec source: <change>/phase/<N>` (phase), written in the call that creates it, so an
  interrupted run can find it again.
- **Local references.** The container is recorded in `.openspec.yaml` with the real values the
  tracker returned. A phase's issue reference goes at the end of its heading:
  `### Phase 1: Durable order ids [ABC-123]`. Write each one as soon as the tracker returns it.
- **Resolve the container.** Use the user's choice or the recorded one; if they conflict, ask.
  With neither, create it only after the user agrees. Never bind a container that another
  change, archived ones included, already records.
- **Sync phases.** For a phase with a reference, fetch the issue and update only the managed
  fields that changed (title, description). For a phase without one, search the container,
  closed issues included, for its `OpenSpec source:` line: reuse a single match, ask about
  several, otherwise create it. Renumbered phases keep their issues; update the source line.
  An unchanged sync writes nothing. Phases run in file order; write no dependency relations.
- **Report.** Read back what you wrote. Report the container link, the phases created, updated
  and unchanged, the phases whose state in the tracker disagrees with the checkboxes (left as
  they are), and orphans: issues of the container whose phase no longer exists. Never delete or
  close anything.

## 3. State

The agent writes one thing about progress, at one moment: when apply starts a phase whose
heading has an issue reference, it marks that issue started as the tracker's reference says.
Never move an issue backwards, never write state during a sync or an archive, and never mark
local checkboxes from the tracker. When the user asks to close an issue or mark it done, point
them to the tracker.

Before archiving, run a sync and report every phase whose issue is not finished; the user
decides whether to archive anyway.
