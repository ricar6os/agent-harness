---
name: openspec-explore
description: Think a problem or an idea through before it becomes an OpenSpec change. Use when the user wants to investigate current behaviour, compare approaches or settle scope before proposing. Writes no code and no change.
---

# Explore before proposing

Exploring ends in a shared understanding, held in the conversation. Change files come later, from `openspec-propose`, and code from `openspec-apply-change`.

## 1. Ground the question

Read what bears on the question before asking the user anything:

- `openspec list --specs`, and the main specs of the capabilities involved.
- `openspec list`, for active changes that touch the same capabilities.
- The code and the tests of the repos involved. Read each repo's own instructions first, as [working-on-a-repo.md](../../../docs/agents/working-on-a-repo.md) step 2 says.

Done when you can state what the system does today, citing the files that show it.

## 2. Explore with the user

- Ask one question at a time, each with the answer you recommend and why. Ask only what the code cannot answer: intent, priorities, constraints. Verify facts yourself.
- When several approaches fit, compare them by what each costs and what each rules out.
- Track decisions in the conversation, and keep confirmed decisions apart from your proposed defaults: silence is not agreement.

Done when the user says the scope is clear, or chooses to stop.

## 3. Close

Summarise in this order: the decisions made, the open questions, what is out of scope, and the capabilities and repos affected. When the behaviour to change has no main spec, say so and name `openspec-create-spec-from-code` as the step before proposing. Then offer `/openspec-propose <name>`.
