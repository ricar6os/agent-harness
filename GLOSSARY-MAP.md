# Workspace Glossary Map

This meta repository coordinates independent repositories. Domain documentation is organized
by OpenSpec product, with repository-local contexts beneath it when needed. Each
change has its own Linear project, classified by the product label in the `Product` group.
The product is a navigation boundary; its services need not share one domain model.

## Contexts

| Product | Domain entry point                                | Scope                                                                                               |
| ------- | ------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
<!-- | `shop` | [Shop glossary](docs/contexts/shop/GLOSSARY.md) | One-line scope of the product. | -->

[repos.json](repos.json) is authoritative for product membership and checkout paths. Select
entries whose `products` contains the product slug, plus entries without `products` (shared
by all products). Resolve each checkout under the manifest's `root`, using `path` when set
and `name` otherwise. Repository names alone do not determine product membership.

Repository links resolve after syncing the corresponding product. Follow each relevant repo's
own `GLOSSARY-MAP.md` when present, otherwise its root `GLOSSARY.md`, alongside its agent
instructions. Missing glossaries are created lazily when vocabulary is resolved.

## Specifications and decisions

For OpenSpec work, resolve the product using [OpenSpec guide](docs/agents/openspec.md#products-and-linear-projects) and
[OpenSpec configuration](openspec/config.yaml). This map supports navigation; it does not
select a product's work on the user's behalf.

- Main specs: `openspec/specs/<product>/<capability>/spec.md`.
- In-flight changes: select by `x-product:` in `openspec/changes/<change>/.openspec.yaml`,
  then read the relevant proposal, design, delta specs and tasks.
- Repository-local specifications and decisions remain in their owning repository.
- Product-wide ADRs: `docs/contexts/<product>/adr/`.
- Workspace-wide ADRs: `docs/adr/`.
- Repository-local ADRs: `docs/adr/` beneath that repository, or paths in its own glossary map.

Create ADRs only when a decision warrants one. When adding a product or resolving a new
context, update this map with its glossary and relationships; keep repository membership in
the manifest.
