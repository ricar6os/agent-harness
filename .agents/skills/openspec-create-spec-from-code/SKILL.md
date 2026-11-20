---
name: openspec-create-spec-from-code
description: Create the main OpenSpec specs of behaviour that already exists in the code of a product's repos, so the next change can modify or remove it instead of only adding to it.
disable-model-invocation: true
metadata:
  adapted_from: CodelyTV/agent-harness, skill openspec-create-spec-from-code (https://github.com/CodelyTV/agent-harness)
  author: Codely <support@codely.com> (https://codely.com)
  license: MIT
---

# Create OpenSpec specs from existing code

An OpenSpec change can only `MODIFY` or `REMOVE` a requirement that already lives in `openspec/specs/`. Behaviour built before the team adopted OpenSpec has no spec, so every change over it lands as `ADDED` and the spec forgets what was there before. This skill writes that missing **baseline**: main specs for behaviour that already ships, in the namespace of one OpenSpec product.

The baseline is the spec OpenSpec would have archived if the feature had been built with it: **intent that was implemented and verified**. Every sentence holds against the code, and every requirement is something someone meant. A baseline that flatters the code is worse than none, because the next proposal builds on it.

## Input

The argument is free text. Read it as one of these:

| Input | Example | Scope |
| --- | --- | --- |
| Nothing, or a question about what lacks a spec | `which features of shop have no spec?` | The inventory in [`references/evidence-guidelines.md`](references/evidence-guidelines.md#inventory). Build it and stop until the user picks a row. |
| A capability | `order-placement` | That capability. |
| A change the user is about to make | `add discount coupons to order placement` | The current behaviour the change will touch. The new behaviour belongs to the change, not to the baseline. |
| A path or a screen | `repos/api/src/orders` | The business concept that path serves, traced back from it. |

## Steps

### 1. Resolve the product and check the preconditions

- When `repos.json` declares `products`, resolve and announce the OpenSpec product as the `context:` of `openspec/config.yaml` requires: the user's selection; if there is none, list the products from `repos.json` and ask. Never infer it from the code. A capability belongs to one product: behaviour that two products share becomes one capability in each, each described with that product's vocabulary. Without `products`, there is no product: read `<product>/` in every path and id below as empty, and `--product <slug>` as absent.
- Run `scripts/init.sh --product <slug> --no-update`: it clones every repo of the product (those whose `products` contains the slug) and every shared repo that is missing, not only the ones the capability touches, and leaves existing clones exactly as they are. Do not use `make sync`: it moves clean clones to their default branch, which would move a user's feature branch. Evidence is read from whatever branch each clone is on; tell the user when a clone is not on its default branch.
- Run `python3 scripts/check.py --openspec-ok`. When it fails, show its message and stop: the user installs the OpenSpec CLI it names.
- Read the `context:` of `openspec/config.yaml`. Write the specs in English unless it or `AGENTS.md` says otherwise.

Done when the product is announced, its repos are cloned (the user told of any clone off its default branch) and the CLI check passes.

### 2. Bound the capability

- A capability is one folder `openspec/specs/<product>/<capability>/`, named in kebab-case after the business concept (`order-placement`), never after a class, a table, a repo or a folder.
- Run `openspec list --specs`: ids print as `<product>/<capability>`. When a spec of this product already covers part of the behaviour, extend it.
- When the areas involved share no business concept, they are several capabilities: propose the split to the user.
- For a change the user is about to make, list the existing behaviour it will touch and confirm that scope with the user.
- Look for `openspec/changes/*/specs/<product>/<capability>/` in the active changes. When one has a delta on the capability, warn the user that extending the main spec can break that change's archive, and ask whether to go on.

Done when the user has confirmed every capability, and whether each one is new or extended.

### 3. Collect the evidence

Read [`references/evidence-guidelines.md`](references/evidence-guidelines.md) and explore the areas as it describes: one area at a time, reading the repo's own instructions first.

Done when every area of every capability has a report, and every candidate behaviour in it carries its evidence.

### 4. Classify

Sort every candidate behaviour into one of the four cases of [`references/evidence-guidelines.md`](references/evidence-guidelines.md#the-four-cases). Then ask the user about all the **ambiguous** candidates in a single round, as that file describes. Use the tool to question the user if you have one.

Done when every candidate has a case, and every ambiguous one has the user's verdict.

### 5. Write the specs

Read [`references/spec-format.md`](references/spec-format.md) and write `openspec/specs/<product>/<capability>/spec.md` with the **intended and verified** behaviour only, in the terms of the glossaries of the product's repos (a `GLOSSARY.md` or what their instructions point to). A term the code uses and no glossary has does not go into the spec as your own coinage: use the code's word, and list it in the report (repos with no glossary: every domain term). A baseline describes implemented behaviour, and a glossary can describe a proposed model the code does not implement yet. Use the term the shipped product uses (its screens, API and tests); when a glossary proposes a different term for the same thing, keep the implemented term and list the pair in the closing report.

When you extend an existing spec, add requirements and scenarios and keep every existing one exactly as it is. An existing requirement that the code contradicts is **drift**: it goes to the report, and changing it is the job of an OpenSpec change.

Done when every intended and verified candidate is a requirement or a scenario in the spec.

### 6. Validate

Run `openspec validate <product>/<capability> --type spec --strict` for every spec you wrote, fix every error and warning, and rerun. Then run `make check`: its `change-product` rule verifies the spec paths and `openspec-validate` the format.

Done when every spec passes strict validation and `make check` reports `ok`.

### 7. Report and close

Answer in the language the user writes in. Report, in this order:

1. The specs written or extended, each with its id (`<product>/<capability>`).
2. The scope decisions: splits, extensions, what you left out of the scope and why.
3. The candidates you left out of the spec, each with its case and its evidence.
4. The drift between existing requirements and the code, and the disagreements between repos.
5. The terms the code uses and no glossary has, and the pairs where a glossary proposes a different term than the implemented one (implemented term kept).

Do not paraphrase the specs: the files are the deliverable. Then close with the steps that this run's facts call for, in this order, translated to the user's language:

- **Always**, the review:

  ```
  Review <spec paths>: they come from the code, and from now on agents will treat them as the truth. Once you agree with them, commit them in the workspace repo on a branch (for example `docs(openspec): add <product>/<capability> baseline spec`), never in a product repo.
  ```

- **When the input was a change the user is about to make**, the way back to it:

  ```
  With the baseline ready, go on with your change: `/openspec-explore <the change, as the user described it>`
  ```

- **When you left a bug out of the spec**, one ready-to-paste command per bug, with the evidence inline:

  ```
  <n> inconsistencies left out of the spec. To fix one:
  - `/openspec-explore <the behaviour the intent asks for> fails when <the case that breaks> (<repo/file:line>; <the test that covers it, or "no test covers it">)`
  ```

## Boundaries

- Write only under `openspec/specs/<product>/`. Changes, `config.yaml` and the code in `repos/` stay as they are.
- Leave the specs uncommitted: committing comes after the user's review.
