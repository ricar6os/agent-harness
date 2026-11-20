# Evidence guidelines

How to find what the code really does, and how to decide what of it belongs in the spec.

## Authority order

Each source answers a different question, and the later ones correct the earlier ones:

1. **Contracts**: API schemas, route handlers' signatures, public types, event payloads. What the system **promises**.
2. **Implementation**: use cases, domain rules, validations, persistence, screens, their states and their copy. What the system **does**.
3. **Tests**: the **decisive** source. A behaviour a test asserts is verified. When the implementation and a test disagree, the test states the intent.
4. **Docs**: `README`, `AGENTS.md`, `docs/`. Read them first to find the code quickly, and trust them only where the code or a test confirms them. A behaviour that only the docs describe is an aspiration, not behaviour.

## Where the evidence is

The code of the product is in `repos/<name>`, one clone per repo of the product (the repos whose `products` contains the slug, plus the shared ones the capability touches). Before reading a repo, load its instructions: its `<repo>--instructions` skill, or its `AGENTS.md`. They say where the tests live and how the repo names things.

An **area** is usually one repo, or one module of it: a backend context, a set of screens, a worker, an integration. A small capability may live in a single area.

Behaviour that crosses repos is evidenced on **both sides**: the provider's contract and implementation, and the consumer's use of it. When the two sides disagree (a field the consumer reads and the provider never sends, a status code one side does not handle), that is an anomaly to report with both sources. Do not average them, and do not pick a side without a test.

## Exploring

Explore **one area at a time**, yourself. Read the implementation **and the tests** of the area: crossing code against its tests is what surfaces anomalies, so keep them in the same report. Then cross the areas.

Use one explorer subagent per area only when the harness offers subagents and the user's instructions allow them. Give each one its area, the capability, and the report contract below; use a cheaper model than the one running this skill. It reports facts; you decide what goes in the spec.

### Report contract

Each area ends in a list of **candidate behaviours**. Each one carries:

- **Behaviour**: one sentence, as a user or a client of the area observes it.
- **Evidence**: `repos/<name>/<file>:<line>` of the code that implements it.
- **Test**: `repos/<name>/<file>:<line>` of the test that asserts it, or `none`.
- **Values**: the concrete identifiers, inputs and outputs from tests, fixtures or seed data, to write runnable scenarios.
- **Anomaly**: anything that contradicts the rest of the evidence or looks unintended, with both sources, including a disagreement between repos. `none` when everything agrees.

## The four cases

Every candidate behaviour falls into exactly one case. The spec holds only the first one.

| Case | Signal | Example | What happens |
| --- | --- | --- | --- |
| **Intended and verified** | A test asserts it, or the code states it on purpose and nothing contradicts it. | The order service rejects an order with no lines, and a test asserts it. | A requirement, with scenarios built from the test's values. |
| **Bug** | The code contradicts an intent the rest of the evidence makes clear. | An order accepts 5 units of a variant with 3 in stock, while every other path checks the stock. | The requirement states the intent with the scenarios that hold. The scenario that breaks stays out of the spec and goes to the closing as a bug. |
| **Accidental** | Nobody decided it: a side effect of how the code happens to be written. | The admin lists orders in insertion order because the query has no `ORDER BY`. | Out of the spec. |
| **Dead** | Nothing reachable triggers it. | A `cancelOrder` action that no screen or endpoint calls. | Out of the spec, and listed in the report. |

Leave a candidate out at the finest grain that keeps the spec true: one broken scenario removes that scenario, not its whole requirement.

### Ambiguous candidates

A candidate is **ambiguous** when the evidence cannot tell its case: observable behaviour with no test, where intent and accident are both plausible. For example, the order service accepts guest orders and no test or doc says whether that is on purpose.

Classify the clear candidates yourself. Gather every ambiguous one and ask the user in a single round. For each, give the behaviour, its evidence, and your recommended case, and let the user pick:

- **Intended**: it becomes a requirement.
- **Bug**: it stays out of the spec and goes to the closing as a bug.
- **Irrelevant**: it stays out of the spec.

## Inventory

When the user asks what lacks a spec, build this table for the announced product and stop:

1. List the existing capabilities of the product with `openspec list --specs` (ids `<product>/<capability>`).
2. List the business concepts the code of its repos holds: backend contexts or modules, route groups, top-level screens.
3. Join them by business concept, across repos.

| Candidate capability | Code areas | Existing spec |
| --- | --- | --- |
| `order-placement` | `repos/api/src/orders`, `repos/web/src/app/checkout` | none |

Name each candidate in kebab-case after its business concept, and let the user pick the rows to create.
