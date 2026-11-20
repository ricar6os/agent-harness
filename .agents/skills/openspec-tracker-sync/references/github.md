# GitHub

Tools: the `gh` CLI, authenticated (`gh auth status`). Issues live in the repository that holds
`openspec/`, even when a phase touches other repos; get its name with
`gh repo view --json nameWithOwner -q .nameWithOwner` from the folder that holds `openspec/`.
`<repo>` below stands for that `owner/name`.

## Mapping

| OpenSpec | GitHub | Local reference |
| --- | --- | --- |
| Change | One parent issue titled after the plan; its body holds the plan's Goal and a link to the change | `x-github-issue` in `.openspec.yaml` |
| `### Phase N: <slice>` | One sub-issue of the parent, titled `Phase N: <slice>`: the phase's description, repos and tasks as a checklist, a link to `plan.md` | `[#13]` at the end of the heading |
| `x-product` (when the change has one) | A label `product:<slug>` on the parent and every sub-issue | none |

```yaml
x-github-issue:
  repo: <owner/name>
  number: <parent issue number>
  url: <parent issue URL>
```

## Commands

Write bodies to a file from `mktemp -d` and pass them with `--body-file`.

- Find by identity: `gh issue list --repo <repo> --state all --search '"OpenSpec source: <change>/phase/<N>" in:body' --json number,url,state`
- Parent: `gh issue create --repo <repo> --title "<plan title>" --body-file <file>`
- Phase: `gh issue create --repo <repo> --parent <parent number> --title "Phase <N>: <slice>" --body-file <file>`.
  When `gh issue create --help` lists no `--parent`, create the issue, then link it:
  `gh api -X POST repos/<repo>/issues/<parent>/sub_issues -F sub_issue_id=$(gh api repos/<repo>/issues/<number> --jq .id)`
- List the phases: `gh api repos/<repo>/issues/<parent>/sub_issues --jq '.[] | [.number, .state, .title] | @tsv'`
- Update: `gh issue edit <number> --repo <repo> --title ... --body-file <file>`
- Label: create `product:<slug>` with `gh label create` only when it is missing.

## Specifics

- **Started**: when apply starts a phase, read its issue (`gh issue view <number> --repo <repo> --json state,assignees`).
  If it is open and has no assignee, assign it to whoever runs apply: `gh issue edit <number> --repo <repo> --add-assignee @me`.
  Otherwise leave it and mention it.
- **Finished**: the issue is closed. Never close one: PRs say `Part of`, not `Closes`, because a
  phase can have PRs in several repos.
- **PR titles** carry no id. The body links the phase in "Why": `Part of <repo>#13`.
