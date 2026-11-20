# env — per-repo local files that are never committed

Files placed under `env/<repo>/` are symlinked into `repos/<repo>/` by `scripts/init.sh`
after each clone or update. Use it for `.env` files and other secrets each repo git-ignores.

```
env/web/.env.secrets   -> repos/web/.env.secrets
env/api/.env           -> repos/api/.env
```

Everything under `env/<repo>/` except `.gitkeep` and this README is git-ignored.

`init.sh` reads two locations, and the second wins when both hold the same file:

1. `env/` of the **main checkout** of this repository, shared by every linked git worktree
   (`git worktree add`, or a tool that creates one). Put files here so a fresh worktree
   gets them without copying.
2. `env/` of the checkout `init.sh` runs from. Use it for files specific to one worktree.

`META_ENV_DIR=/path` replaces both with a single directory.

Rules:

- Never commit secrets here or in `repos/`. Templates live in each repo (`.env.example`,
  `.env.secrets.example`).
- Add a folder per repo as needed; a missing folder is simply skipped.
- `init.sh` never overwrites a regular file already present in the repo; it warns instead.
