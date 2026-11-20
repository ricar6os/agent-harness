# Spec format

A main spec lives at `openspec/specs/<product>/<capability>/spec.md`. The OpenSpec CLI (pinned in `openspec/cli-version`) parses it by its headings, so this skeleton is the contract that `openspec validate`, `openspec show` and every later change rely on.

```markdown
# <product>/<capability> Specification

## Purpose

<One to four sentences, at least 50 characters: the business concept, who uses it, and what this capability is responsible for.>

## Requirements

### Requirement: <Short name of one behaviour>
<Normative sentence with SHALL or MUST, up to 500 characters, holding the concrete constraints: limits, formats, ordering, status codes.>

#### Scenario: <The main case>
- **WHEN** <a concrete action with concrete values>
- **THEN** <the observable result, with the concrete values expected>

#### Scenario: <The error or edge case>
- **WHEN** ...
- **THEN** ...
```

## Product, id and commands

Checked with CLI 2.1.1:

- The id is the path under `openspec/specs/`. `openspec list --specs` prints `<product>/<capability>`, and every command takes that id. The bare `<capability>` is not found.
- Validate one spec: `openspec validate <product>/<capability> --type spec --strict`. Without `--strict`, warnings pass; with it they fail.
- The CLI does not read the title line. Write `# <product>/<capability> Specification` so a reader sees the same id the CLI prints.

## Rules the parser relies on

- One `## Purpose` and one `## Requirements`. A Purpose under 50 characters, or a placeholder such as `TBD`, is a warning, and warnings fail `--strict`.
- Every requirement heading starts with `### Requirement: `, and its text holds `SHALL` or `MUST`.
- The text of a requirement, between its heading and its first scenario, stays within 500 characters. Longer text is a warning: move examples and edge cases into scenarios, or split the requirement.
- Every requirement has at least one `#### Scenario: ` with a `- **WHEN**` and a `- **THEN**` bullet. `- **AND**` bullets may follow either.
- Requirement names are unique in the spec: later changes reference them by name.
- A main spec states behaviour, so it uses only `## Requirements`. The `ADDED`, `MODIFIED`, `REMOVED` and `RENAMED` sections belong to the delta specs of a change.
- The structural headings and the `SHALL`/`MUST` keywords stay in English whatever language the spec is written in.

## What makes a baseline useful

**The normative voice.** Write `SHALL` about present behaviour. From now on the spec is the promise, and the next change proposes a delta against it. Wording such as "currently" or "the code does" marks the text as a snapshot, and the next author cannot tell what is still guaranteed.

**One requirement, one behaviour.** Split when a client would test two behaviours separately. Merge when splitting would repeat the same normative sentence.

**Concrete values.** Scenarios name the identifiers, quantities and texts found in tests, fixtures and seed data, so a reader can run them against the application. "An invalid request is rejected" cannot be run; "a quantity above the 3 units in stock is rejected with the message 'Not enough stock'" can.

**Observable behaviour only.** Tables, classes, folders, repos and frameworks stay out. Persistence is observable as "survives a reload", not as "stored in the `orders` table". Behaviour across repos is stated as the product observes it, not as which service calls which.

**The product's words.** Use the terms of the repos' glossaries, when they have one. Do not coin a term the code does not use. A baseline describes implemented behaviour, so it uses the term the shipped product uses (its screens, API and tests). When the glossary proposes a different term for the same thing, keep the implemented term and list the pair in the closing report.

## Example

```markdown
### Requirement: Stock limits the quantity in the cart
The shop SHALL reject adding a quantity of a variant above its available stock, and SHALL keep the cart unchanged.

#### Scenario: Quantity within the stock
- **WHEN** a shopper adds 2 units of "Pure Function Tee" Black / M, which has 3 units in stock
- **THEN** the cart holds 2 units of that variant

#### Scenario: Quantity above the stock
- **WHEN** a shopper adds 5 units of "Pure Function Tee" Black / M, which has 3 units in stock
- **THEN** the shopper sees "Not enough stock" and the cart is unchanged
```
