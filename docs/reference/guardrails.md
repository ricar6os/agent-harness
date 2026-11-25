# Guardrails reference

What `scripts/guard.py` blocks, for which agents, and what it leaves alone.

## Guardrails

`AGENTS.md` asks agents to ask first before merging, force-pushing or deleting branches, never to
commit to a default branch and never to put secrets in the conversation. The parts of that a
tool-call hook can decide exactly are enforced by `scripts/guard.py` (Python standard library
only): one function, `decide(tool, tool_input, cwd, root)`, answers `allow`, `ask` or `deny` with
a reason, and a thin adapter per agent speaks that agent's hook format. The rule is **exact or
skip**: it blocks only what is certainly the forbidden action, because a guard that guesses
trains people to bypass it. An internal error allows the call and prints one line on stderr.

| Decision | What | Why the agent is told |
| -------- | ---- | --------------------- |
| ask | `git push` with `--force`, `-f`, `--force-with-lease`, `--force-if-includes` or a `+refspec` | force-push rewrites remote history |
| ask | `git push --delete`/`-d` or a `:branch` refspec | deletes a remote branch |
| ask | `git branch -d`/`-D`/`--delete` | deletes a branch |
| ask | `gh pr merge`, also behind global flags (`gh -R owner/repo pr merge 12`); `--help` is allowed | merging is the user's decision |
| deny | `git commit` on the default branch of the target repository | create a branch first (`git -C <dir> checkout -b <type>/<short-slug>`) |
| deny | `git push` from the default branch, or to it (`main`, `HEAD:main`, `x:main`) | open a PR instead |
| deny | reading or writing a secret file (`env/**` except `env/README.md` and `.gitkeep`; `.env`, `.env.*` except `.example`, `.sample`, `.template`, `.dist`; names are matched case-insensitively, as macOS file systems are) with a file tool (`Write`, `Edit`, `apply_patch` included), or printing it with `cat`, `grep`, `sed`, `jq`, `open`, `vim` and similar | secret values stay out of the conversation; read the `.example` template |
| deny | `env`, `printenv`, `export` or `export -p`, `declare -x`, `set` with no arguments | dumps every variable, tokens included; use `printenv NAME` |
| deny | an edit with a file tool (`Edit`, `Write`, `MultiEdit`, `NotebookEdit`, `apply_patch`) under `repos/<name>/` while the session has not read the instructions of that clone (see "Repository instructions") | read the file it names, then repeat the edit; there is nothing to ask the user |

The default branch of a clone is the `branch` of its `repos.json` entry (`main` when omitted);
anywhere else it is `origin/HEAD`, or `main`/`master` when that is the current branch. Outside a
git repository, on a detached HEAD, or when the branch cannot be told, nothing is blocked. A
commit or push that follows `git checkout <branch>`, `git checkout -b`, `git switch <branch>`, `git switch -c`
or `git checkout -t origin/<branch>` in the same command line counts as running on that branch (a name that is
a file and not a branch, `.`, `HEAD~1`, `-`, `--detach`, `git checkout -p` or `git checkout <tree-ish> -- <paths>` leaves it as it was or unknown). A new repository with no commit
and no `origin` has nothing to protect: its first commit is allowed. `cd <dir>` and `git -C <dir>` are followed,
as are `( ... )` subshells (only an unquoted parenthesis where a command starts opens one; a `)` in a quoted message or in `$( ... )` does not close it), `{ ...; }` groups, the commands after `do`, `then` and `else`, the command that `env [NAME=value] ...` wraps, and `bash -c '<literal string>'` (a checkout inside them counts for the rest of the line, a `cd` does not); redirections such as `2>&1` are not arguments; heredoc bodies are data and are not read as commands, unless the heredoc feeds a shell (`sh <<EOF`, `bash -s arg <<EOF`, `cat <<EOF | bash`), whose body is read like `bash -c`.
`git push --tags` alone is allowed; `--follow-tags` pushes the branch too. Moving,
copying, linking, removing, `source`-ing a secret file or passing it to `--env-file` is allowed:
those do not print values.

## Repository instructions

From the meta root no agent loads `repos/<name>/AGENTS.md` reliably, and the `<repo>--instructions`
skill ([skills.md](skills.md), "Per-repo instructions") only asks for the read. The guard makes it a
condition: the first edit under `repos/<name>/` is denied until the session has read every
instructions file of that clone. Those are the files the skill lists: `AGENTS.md`, and `CLAUDE.md`
when it says more than `@AGENTS.md`. A clone with neither is never blocked. The folder of the
clones is the `root` of `repos.json`.

A read is the read tool on the file, or a shell command that shows it (`cat`, `head`, `tail`,
`less`, `more`, `bat`, `nl`, `tac`, `sed` without `-i`) and that the guard allows. `grep`, `wc` and
`ls` show no rules, so they do not count. The deny names the files to read and tells the agent to
read them and repeat the edit without asking the user: this is the one block that the agent
resolves by itself.

Each hook call is a new process, so a read is kept as an empty marker file under
`agent-guard-<uid>/` in the system's temporary directory, in a folder per session. What each
agent sends decides how far the rule reaches:

| Agent | Session | Subagents | After a compaction |
| ----- | ------- | --------- | ------------------ |
| Claude Code | `session_id` | each has its own reads (`agent_id`), as it has its own context | the `PostCompact` hook of `.claude/settings.json` forgets the reads, so the next edit asks for them again |
| Codex | `session_id` | not checked | the reads are kept |
| OpenCode | `sessionID`, which the plugin passes on | not checked | the reads are kept |

The block, the read and the repeated edit were run end to end with Claude Code 2.1.332, Codex
0.172.0 and OpenCode 2.4.1 on macOS.

A call that names no session is not blocked, and neither is a session whose markers cannot be
written. An edit made by a shell command (`sed -i`, a redirection, a script) is not seen: like the
rest of the guard, the rule covers what it can decide exactly.

| Agent | Enforced through | `ask` |
| ----- | ---------------- | ----- |
| Claude Code | `.claude/settings.json`, a `PreToolUse` hook on `Bash`, `Read`, `Edit`, `Write`, `MultiEdit` and `NotebookEdit`, and a `PostCompact` hook (see "Repository instructions") | the user is prompted to confirm |
| Codex | `.codex/hooks.json`, a `PreToolUse` hook on shell commands and `apply_patch`; the hook walks up from the session directory to the nearest folder holding `repos.json` and `scripts/guard.py`, so it runs this workspace's script even from inside `repos/<name>`, and does nothing when there is none. Codex loads project hooks only from a trusted project and asks you to review the hook (`/hooks`) once | hooks cannot ask: the call is blocked with a reason telling the agent to ask you to run the command or confirm |
| OpenCode | `.opencode/plugins/guard.js`, a plugin hook on `tool.execute.before`. A plain object with no package import, only Node built-ins (see below) | same as Codex: blocked, with the same reason |

Any other agent is not enforced.

A blocked call means stop and ask the user; look for no other route to the same effect. The
exception is the block that asks for a clone's instructions: read them and repeat the edit. To see
why a command is blocked, or whether it would be:

```bash
scripts/guard.py --explain 'git push --force origin main'   # prints "deny: ..." / "ask: ..." / "allow"
```

`--explain` runs the command as if typed in the current directory (it follows `cd` and `git -C`).

Deliberately **not** enforced, because no hook can decide it exactly: changes to production
infrastructure, removing entries from `repos.json`, and secrets printed by a program the agent
runs (a script that echoes its `.env`, `docker inspect`, a server log). Those stay with the
"ask first" list in `AGENTS.md`. Also out of reach: commands built at run time (`bash -c "$X"`, a
`bash -c` string with `$` or a backtick inside, `eval`, `$(...)`, `xargs`), a script file the agent writes and
then runs, and anything an agent does through another tool. This prevents mistakes; it is not a
sandbox, and a determined agent or person can get around it.

The OpenCode plugin is a plain `export default { id, setup }` object that imports only Node
built-ins, so a fresh clone needs no package install. It was verified with OpenCode 2.3.2 on
macOS, and the session it passes with 2.4.1; other versions were not tried.

The `guardrails` check keeps the wiring in place. Changes to `scripts/guard.py` come with rows in
`tests/test_guard.py`: one for what it blocks and one for the look-alike it must still allow.
