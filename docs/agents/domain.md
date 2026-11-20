# Domain Docs

Layout: **multi-context**. The root [glossary map](../../GLOSSARY-MAP.md) routes to product
glossaries, repository-local contexts, specifications and decisions across this workspace.
Products define domain scope; each change has its own separate Linear project.
A change stays within one product, including when it touches shared repositories.

## Before exploring

1. Read `GLOSSARY-MAP.md` at the meta root and follow the entry points relevant to the task.
   Use `repos.json` for product membership and checkout paths. For OpenSpec operations,
   resolve the product according to [openspec.md](openspec.md) before selecting its specs.
2. Read the relevant product glossary and each affected repository's own `GLOSSARY-MAP.md`
   or `GLOSSARY.md`, following its agent instructions. A repository can contain several
   contexts, and a domain model can span several repositories.
3. Read relevant ADRs at the workspace, product and repository scopes listed in the map.
4. Read the applicable main specs and in-flight changes. Distinguish proposed vocabulary
   and behavior from implemented behavior using tasks and code; a delta spec alone does
   not establish that a migration has shipped.

If a glossary or ADR directory does not exist, proceed silently. The `domain-modeling` skill
creates it when terms or decisions are resolved. Read repository-local specs when directed
by that repository's instructions.

## Where to write

| Scope                       | Glossary                                                         | Decisions                                                 |
| --------------------------- | ---------------------------------------------------------------- | --------------------------------------------------------- |
| Across products             | Meta root `GLOSSARY.md`, only for genuinely shared vocabulary    | Meta root `docs/adr/`                                     |
| Across repos in one product | `docs/contexts/<product>/GLOSSARY.md`                            | `docs/contexts/<product>/adr/`                            |
| Within one repo             | That repo's root `GLOSSARY.md`, or paths in its own glossary map | That repo's `docs/adr/`, or paths in its own glossary map |

Reuse an existing glossary in its owning repo when it covers a product's context; the map
links to it instead of copying it into meta. Repository-local files are committed in their
own repository. OpenSpec behavior and implementation plans stay in OpenSpec artifacts;
`GLOSSARY.md` files contain domain vocabulary only.

## Use scoped vocabulary

Use each context's canonical terms in issues, designs, code and tests. Preserve distinctions
when contexts use the same word differently. Document translations at their boundary instead
of imposing a workspace-wide synonym. Resolve new terms with `domain-modeling` and update
the map when a new context or relationship is established.

## Flag ADR conflicts

If a proposal contradicts an applicable ADR, cite the decision and explain the conflict
explicitly rather than silently overriding it.
