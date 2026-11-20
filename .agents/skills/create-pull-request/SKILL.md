---
name: create-pull-request
description: Write the title and body of a pull request, with before/after evidence, deploy steps and rollback, and link the PRs of a change that spans repos. Use before creating or editing a pull request, and after pushing commits to a branch that has an open pull request.
metadata:
  adapted_from: CodelyTV/agent-harness, skill create-pull-request (https://github.com/CodelyTV/agent-harness)
  author: Codely <support@codely.com> (https://codely.com)
  license: MIT
---

# create-pull-request

A reviewer must understand, verify and undo the PR without opening the code. A change that spans repos is several PRs: each one must show where it sits among the others.

## 1. Which rules apply

1. The rules of the repo the PR is opened in come first: its `.github/pull_request_template.md` and the PR rules in its `AGENTS.md`. They decide the length and which sections exist.
2. Use [`references/pull-request-template.md`](references/pull-request-template.md) only when the repo has no template. Fill what the repo's rules leave open.
3. When the repo asks for short descriptions, or only non-obvious things, keep only the sections that carry something non-obvious, each in its shortest form. Two sections are non-obvious by nature and stay: **Related PRs** for a change that spans repos, and **Deploy steps** / **Rollback** when shipping touches state outside the code (migrations, config, data, a manual step).
4. Add those sections to the repo's own template when they apply, unless the repo's instructions forbid extra sections.

## 2. Title

Conventional Commits, `type(scope): description`, unless the repo's rules set another format. If the repo restricts scopes (a script, config or CI check validates titles), use one of them.

When the PR implements a phase of a plan, the phase's issue reference sits at the end of its heading in `plan.md`, and its form decides where it goes:

- A tracker id such as `[ABC-123]` is the first word of the description: `feat(login): ABC-123 add magic-link sign-in`.
- A GitHub issue such as `[#13]` stays out of the title and goes in the body ("Why").
- No reference: a plain title.

## 3. Body

`gh pr create --body` ignores templates. Shell variables do not survive between tool calls, so run `mktemp -d` once, note the absolute path it prints, and write that literal path in every later command; `<tmp>` below stands for it. Copy the template to `<tmp>/pr-body.md`, fill it, delete the sections that do not apply and every HTML comment, and pass it with `--body-file`. Remove the directory when done (`rm -r <tmp>`).

- **Why**: the problem, not the solution, in product vocabulary. When the PR implements a phase of a plan, link the change and, when there is one, the phase's issue: the tracker's issue, or `Part of <owner>/<repo>#13` for a GitHub issue. Write `Part of`, not `Closes`: a phase can have PRs in several repos. The change link is the URL of the change's folder (`openspec/changes/<change>/`) in the repo that holds it, on its default branch (`gh repo view --json url,defaultBranchRef`, run in that repo), or on the change's branch while it is unmerged.
- **What changes**: 2-5 bullets: what changes for users or operators, and what a reviewer must know (decisions, trade-offs, non-obvious effects). Never the commit list.
- **Related PRs** (only for a change that spans repos): the PRs of this PR's phase, in the order of that phase's `**Repos:**` line in the change's `plan.md`, each with its link or "not opened yet"; mark this one. One line names the earlier phases as already shipped or still open. A repo that is only touched conditionally is listed with its condition. One sentence: what must be merged and deployed before this PR, and what waits for it. When the phase has no such line, use provider before consumer and say in the PR that the order was inferred.
- **Evidence**: proves the change that "Why" describes, with the same input before (base branch) and after. Pick by kind of change:
  - Behaviour without a screen (API, job, script, agent tool): request and response, or command and output, in code blocks trimmed to the relevant fields.
  - A contract another repo consumes (API schema, event payload, table): the diff of the contract as declared in the Contracts of the phase in the change's `plan.md` (the contract diff when the phase declares none).
  - A screen: screenshots at desktop 1440 px and mobile 390 px on both sides, same viewport and crop. Never commit them; attach them (section 4).
  - A change in how components call each other: optional Before/After Mermaid diagrams with the same node names.

  For a fix, the "before" showing the failure matters most. Delete the section only when nothing outside the tests can observe the change (config, CI, docs, an internal refactor). Evidence never contains tokens, credentials, connection strings or personal data from dev copies of production data: trim or redact, and say what was redacted.
- **How I verified**: the commands actually run and their real result, including the repo's verification command (the one its `AGENTS.md` or the workspace's instructions name); and what was not checked. Never list a check that was not done.
- **Deploy steps** (only when someone must act by hand): numbered checkboxes, each with when to run it (before merging / after deploying), where, and the exact command, query or flag. Never tick a box you did not run.
- **Rollback**: "Revert this pull request." when that is enough. Otherwise ordered steps with the exact migration name, command or flag, what data is lost or kept, and what cannot be undone. Read the migrations in the diff; never guess. For a multi-repo change, say where this PR sits in the reverse order: consumers are rolled back before the provider they depend on.

## 4. Create it

Run it from inside the repo the branch belongs to. Take `<owner>/<name>` from `git remote get-url origin` there:

```bash
gh pr create --repo <owner>/<name> \
  --title "feat(scope): ABC-123 description" \
  --body-file "<tmp>/pr-body.md" \
  --assignee @me \
  --attach "<tmp>/evidence/before-desktop.png"
```

- Add `--assignee @me` only when `gh` runs with the credentials of the person directing the work; otherwise leave the assignee empty and say so.
- One `--attach` per image, same absolute path as in the body's Markdown image reference. Check first that `gh pr create --help` lists `--attach`.
- After creating or editing, read the body back (`gh pr view <number> --repo <owner>/<name> --json body -q .body`) and make sure no local filesystem path remains. When `--attach` is unavailable or an upload fails, remove the image reference from the body and tell the user the file paths instead.
- Stop after opening the PR. Merging is the user's decision.

## 5. After creating it

For a multi-repo change:

1. Record the branch and PR in the change's `plan.md`, as a line under the phase's `**Repos:**` line: `PR: <repo> <branch> <url>`.
2. Update "Related PRs" in each sibling PR of the same phase that is already open, so the PRs of that phase show the same list. Edit only PRs of the same phase that are recorded under that phase in the change's `plan.md`; PRs of other phases keep their own list. Always pass the PR number: `gh pr view <number> --repo <owner>/<other> --json body -q .body > <tmp>/other-body.md`, change only its "Related PRs" section, then `gh pr edit <number> --repo <owner>/<other> --body-file <tmp>/other-body.md`.

## 6. After each push to a branch with an open PR

1. This runs in a later session: run `mktemp -d` again, note the new absolute path (`<tmp>`), and remove the directory when done. Read the current body (`gh pr view <number> --repo <owner>/<name> --json body -q .body > <tmp>/pr-body.md`) and start from that file. Compare each section with the full diff against the base branch.
2. Rewrite only the sections this skill owns that changed, so the body describes the current state of the whole PR. Never append a changelog. Keep any text, checkbox state or bot content this skill did not write (reviewer notes, ticked boxes, bot summaries).
3. Add or delete Evidence, Deploy steps, Rollback and Related PRs as the diff now requires.
4. Apply with `gh pr edit <number> --repo <owner>/<name> --body-file`, adding `--attach` for new images, then read the body back as in section 4.

## 7. Footer

If the tool adds an attribution footer to the body, keep it as the last line.
