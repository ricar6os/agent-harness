---
name: "<!-- change name -->"
description: "<!-- one sentence -->"
created_at: "<!-- YYYY-MM-DDTHH:MM:SSZ -->"

created_by:
  tool: "<!-- e.g. Claude Code, Codex -->"
  model:
    name: "<!-- e.g. Claude Opus -->"
    version: "<!-- e.g. 5.5 -->"
    reasoning_effort: "<!-- low | medium | high -->"
---

# <!-- Plan title -->

## Goal

<!-- 1-3 sentences: what gets built and why it matters -->

## Decisions

- <!-- choice or assumption (instead of <discarded alternative>, when not obvious) -->
- Out of scope: <!-- what this change does not do -->

## Phases

### Phase 1: <!-- vertical slice -->

<!-- What this phase delivers -->

**Repos:** <!-- api → web (multi-repo workspaces only) -->

**Contracts**

```<!-- language -->
<!-- Contract type (provided by <repo>), as a comment -->
<!-- signature -->
```

**Tests**

- `<!-- test suite -->`: <!-- behaviours it covers -->

- [ ] <!-- repo: task -->
- [ ] Run the verification command of every repo this phase touched and check the phase's behaviour in the running app. Fix issues if any.

## Next step

Run `/openspec-apply-change` to implement Phase 1.
