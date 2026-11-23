# Skills reference

The kinds of skills in a meta workspace and how repo skills reach the agents.

## Skills

- **Root skills** live in `.agents/skills/` (canonical), each with a symlink in `.claude/skills/`. Three kinds:
  - _Custom_: written here and installable elsewhere with `npx skills` (groups in
    `skills.sh.json`). `create-pull-request` (adapted from CodelyTV/agent-harness, MIT) writes the
    title and body of a PR with evidence, deploy steps, rollback and links between the PRs of a
    phase; `openspec-tracker-sync` mirrors phases to the tracker; `unslop` edits writing;
    `sync-repos` clones and updates the repos, and only works in a meta.
  - _Vendored_ (`create-rule`, `deterministify`, `openspec-create-spec-from-code` from
    [CodelyTV/agent-harness](https://github.com/CodelyTV/agent-harness)): upstream skills pinned
    in `skills-lock.json`, never edited here. Update one with `npx skills update <name>`.
  - _OpenSpec's workflow skills_ (`openspec-propose` and the others): installed in a meta by
    `openspec init --scope project`, owned by that meta. To change what they do, change the
    schema or `openspec/config.yaml`.
- **Per-repo skills**: `repos/<name>/.agents/skills/` (or `.claude/skills/`), owned by each
  repository. Neither tool offers them from the meta root on its own: Claude Code loads skills
  below the start directory only once it touches a file there (and in our tests never from the
  git-ignored `repos/`), and Codex only reads `.agents/skills/` from the working directory
  upwards. `make sync` (or `make skills` alone)
  runs `scripts/link-skills.sh`, which links each one as `<repo>--<skill>` into
  `.claude/skills/` and `.agents/skills/` (git-ignored; the repo keeps the only copy). A git
  worktree without its own clone of a repo links to the main checkout's clone. Both tools name
  a skill after its frontmatter, so each name is linked once: meta's own skill wins, and among
  repos the copy with the most recent commit wins; the script prints each skipped skill. A
  skill that several repos install from the same `skills-lock.json` source is linked as
  `shared--<skill>`, since it belongs to none of them.
- **Per-repo instructions**: from the meta root, Codex never loads `repos/<name>/AGENTS.md`, and
  Claude Code attaches it to a tool result that models sometimes discard. So the same script
  generates a `<repo>--instructions` skill for each clone that is in the manifest and has
  instructions (an `AGENTS.md`, or a `CLAUDE.md` with more than an `@AGENTS.md` import) or a
  `check` command, and for each clone that is not in the manifest but has instructions. It tells
  the agent to read those files and, when a `check` is declared, to verify changes with
  `make repo-check REPO=<name>` (in a worktree that has not cloned the repo, it says to run
  `make sync ONLY=<name>` first). A manifest repo with a `check` but no instructions gets a skill
  that says it has no `AGENTS.md`. A clone with neither instructions nor a `check` gets no skill;
  `make status` lists it as without instructions. Skills are listed up front by
  every harness, so this works the same in Claude Code, Codex and others. Start a new agent
  session after linking to pick up new skills.
