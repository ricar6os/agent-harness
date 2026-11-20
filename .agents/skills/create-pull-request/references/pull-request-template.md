## Why

<!-- The problem, not the solution, in product vocabulary, 1-3 sentences. Link the OpenSpec change and the phase's issue, if any (GitHub: `Part of owner/repo#13`). -->

## What changes

<!-- 2-5 bullets a reviewer must know: decisions, trade-offs, non-obvious effects. Never the commit list. -->

- `<item>`

## Related PRs

<!--
Only for a change that spans repos; delete otherwise.
List the PRs of this PR's phase, in the order of that phase's `**Repos:**` line in the change's plan.md, each with its PR link or "not opened yet" (in backticks if left as a placeholder). Mark this one.
One line names the earlier phases as already shipped or still open.
Then one sentence: what must be merged and deployed before this PR, and what waits for it.
-->

1. `<repo>`: `<PR link, or "not opened yet">`
2. `<repo>`: `<PR link, or "not opened yet">` (this PR)

## Evidence

<!--
Proves the change that "Why" describes: same input before (base branch) and after. For a fix, the "before" showing the failure matters most.
- Behaviour without a screen (API, job, script, agent tool): request and response, or command and output, in code blocks trimmed to the relevant fields.
- Contract another repo consumes (API schema, event payload, table): the contract diff.
- Screen: screenshots at desktop 1440 px and mobile 390 px on both sides, same viewport and crop. Attach them with `gh ... --attach`; never commit them.
- Change in how components call each other: optional Before/After Mermaid diagrams with the same node names.
Delete the section only when nothing outside the tests can observe the change (config, CI, docs, an internal refactor).
-->

**Before** (`<base branch>`):

`<same input and its output>`

**After** (this branch):

`<same input and its output>`

## How I verified

<!-- Commands actually run and their real result, including `make repo-check REPO=<name>` (the workspace repository: `make check` and `make test`); and what was not checked. Never list a check that was not done. -->

- `<item>`

## Deploy steps

<!--
Only when someone must act by hand; delete otherwise.
Numbered checkboxes, in order. Each one: when to run it (before merging / after deploying), where, and the exact command, query or flag. Never tick a box you did not run.
-->

1. [ ] **Before merging:** `<where, and the exact command, query or flag>`
2. [ ] **After deploying:** `<where, and the exact command, query or flag>`

## Rollback

<!--
"Revert this pull request." when that is enough. Otherwise ordered steps with the exact migration name, command or flag, what data is lost or kept, and what cannot be undone. Read the migrations in the diff; never guess.
Multi-repo change: say where this PR sits in the reverse order (consumers are rolled back before the provider they depend on).
-->

Revert this pull request.
