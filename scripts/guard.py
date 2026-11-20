#!/usr/bin/env python3
"""Agent guardrails: one decision function, three agent adapters.

`decide(tool, tool_input, cwd, root)` returns ("allow" | "ask" | "deny", reason). It blocks only
what is certainly a forbidden action ("exact or skip"): force-pushes, branch deletion, PR merges,
commits and pushes on a default branch, and reads of secret files or of the whole environment.
It prevents mistakes; it is not a sandbox (see README.md, section "Guardrails").

    guard.py --agent claude|codex|opencode   read one tool call on stdin, answer in that agent's format
    guard.py --explain '<shell command>'     print the decision for a command run in the current directory

Any internal error allows the call and prints one line on stderr: a broken guard never blocks work.
Python 3.9+, standard library only.
"""
import argparse
import glob
import json
import os
import re
import shlex
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.dirname(SCRIPTS_DIR)

SECRET_REASON = ("secret values stay out of the conversation. Ask the user for the value you need, "
                 "or read the `.example` template.")
MAIN_BRANCH_REASON = "never commit or push directly to the default branch (%s)."
ENV_DUMP_REASON = ("dumps every environment variable, tokens included; "
                   "print the one variable you need with `printenv NAME`.")
ASK_HINT = "ask the user to run this command themselves or to confirm"

FILE_TOOLS = {"read", "edit", "write", "multiedit", "notebookedit"}
PATCH_TOOLS = {"apply_patch", "patch"}
SHELL_TOOLS = {"bash", "shell", "exec_command", "local_shell"}
PATH_KEYS = ("file_path", "filePath", "notebook_path", "path")
PATCH_KEYS = ("command", "patchText", "patch", "input")
PATCH_PATH_RE = re.compile(r"^\*\*\* (?:Add File|Update File|Delete File|Move to):\s*(.+?)\s*$", re.M)

PRINTERS = frozenset("""cat head tail less more bat nl tac grep egrep fgrep rg ag awk sed cut sort uniq
strings xxd od hexdump base64 jq yq open code vim vi nano emacs diff cmp""".split())
WRAPPERS = ("command", "sudo", "time", "nohup", "nice")
NICE_OPTION_RE = re.compile(r"^(?:-n?-?[0-9]+|--adjustment=-?[0-9]+)$")
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
SEVERITY = {"allow": 0, "ask": 1, "deny": 2}

PUSH_OPTIONS_WITH_VALUE = ("--repo", "--receive-pack", "--exec", "--push-option", "-o")

UNKNOWN = object()  # a branch we cannot know (for example after `git switch -`)


# ---------------------------------------------------------------------------------------------
# secret files
# ---------------------------------------------------------------------------------------------

def _check():
    if SCRIPTS_DIR not in sys.path:
        sys.path.insert(0, SCRIPTS_DIR)
    import check
    return check


def is_env_secret_name(base):
    """The definition shared with rule `tracked-secrets` of scripts/check.py."""
    return _check().is_env_secret_name(base)


def _under(path, directory):
    path, directory = path.lower(), directory.lower()   # case-insensitive file systems (macOS)
    return path == directory or path.startswith(directory.rstrip(os.sep) + os.sep)


def is_secret_path(path, cwd, root, include_dir=False):
    """True when `path` (resolved against cwd, existing or not, symlinks followed) is a secret file."""
    if not path or "\0" in path:
        return False
    path = os.path.expanduser(path)
    absolute = os.path.normpath(os.path.join(cwd, path))
    candidates = {absolute}
    try:
        candidates.add(os.path.realpath(absolute))
    except OSError:
        pass
    env_dirs = {os.path.join(root, "env"), os.path.join(os.path.realpath(root), "env")}
    for candidate in candidates:
        base = os.path.basename(candidate)
        if is_env_secret_name(base):
            return True
        for env_dir in env_dirs:
            if candidate.lower() == env_dir.lower():
                if include_dir:
                    return True
            elif (_under(candidate, env_dir) and base.lower() != ".gitkeep"
                  and candidate.lower() != os.path.join(env_dir, "README.md").lower()):
                return True
    return False


def _patch_paths(tool_input):
    paths = []
    for key in PATCH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, list):
            value = "\n".join(str(v) for v in value)
        if isinstance(value, str):
            paths.extend(PATCH_PATH_RE.findall(value))
    return paths


def decide_file_tool(tool, tool_input, cwd, root):
    if tool in PATCH_TOOLS:
        paths = _patch_paths(tool_input)
    else:
        paths = [tool_input[k] for k in PATH_KEYS if isinstance(tool_input.get(k), str)]
    for path in paths:
        if is_secret_path(path, cwd, root):
            return "deny", SECRET_REASON
    return "allow", ""


# ---------------------------------------------------------------------------------------------
# shell command parsing
# ---------------------------------------------------------------------------------------------

HEREDOC_MARK_RE = re.compile("\ue000(\\d+)\ue001")


def _skip_arithmetic(command, i):
    """Index after the `((...))` that starts at command[i]; the end of the text when it never closes."""
    depth, j = 0, i
    while j < len(command):
        if command[j] == "(":
            depth += 1
        elif command[j] == ")":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return j


def extract_heredocs(command):
    """(command without heredoc operators and bodies, bodies as [(text, quoted delimiter)]).

    Each `<<WORD` / `<<-WORD` is replaced by a marker that names its body; the command that owns the
    heredoc stays. A heredoc operator is only recognised where the shell would: outside quotes, outside
    `$(( ))` and `(( ))`, and not in a comment. `<<<` here-strings are not heredocs. When in doubt, nothing
    is stripped."""
    out, pending, bodies = [], [], []
    quote = None
    i, n = 0, len(command)
    while i < n:
        c = command[i]
        if quote == "'":
            out.append(c)
            if c == "'":
                quote = None
        elif quote == '"':
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(command[i + 1])
                i += 1
            elif c == '"':
                quote = None
        elif c == "\\" and i + 1 < n:
            out.append(c)
            out.append(command[i + 1])
            i += 1
        elif c in "'\"":
            quote = c
            out.append(c)
        elif c == "(" and command.startswith("((", i):   # arithmetic: `<<` is a shift there
            end = _skip_arithmetic(command, i)
            out.append(command[i:end])
            i = end
            continue
        elif c == "#" and (i == 0 or command[i - 1] in " \t\n;&|("):   # a comment runs to the end of the line
            end = command.find("\n", i)
            end = n if end < 0 else end
            out.append(command[i:end])
            i = end
            continue
        elif c == "<" and command.startswith("<<", i) and not command.startswith("<<<", i) and (i == 0 or command[i - 1] != "<"):
            j = i + 2
            dash = j < n and command[j] == "-"
            j += 1 if dash else 0
            while j < n and command[j] in " \t":
                j += 1
            word, quoted = [], False
            while j < n and command[j] not in " \t\n;&|()<>":
                if command[j] in "'\"":
                    end = command.find(command[j], j + 1)
                    end = n if end < 0 else end
                    word.append(command[j + 1:end])
                    quoted = True
                    j = end + 1
                elif command[j] == "\\" and j + 1 < n:
                    word.append(command[j + 1])
                    quoted = True
                    j += 2
                else:
                    word.append(command[j])
                    j += 1
            if word:
                bodies.append(["", quoted])
                pending.append(("".join(word), dash, len(bodies) - 1))
                out.append(" \ue000%d\ue001 " % (len(bodies) - 1))
                i = j
                continue
            out.append(c)
        elif c == "\n" and pending:
            out.append(c)
            i += 1
            for word, dash, index in pending:
                lines = []
                while i < n:
                    end = command.find("\n", i)
                    line = command[i:] if end < 0 else command[i:end]
                    i = n if end < 0 else end + 1
                    if (line.lstrip("\t") if dash else line) == word:
                        break
                    lines.append(line.lstrip("\t") if dash else line)
                bodies[index][0] = "\n".join(lines)
            pending = []
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out), [tuple(b) for b in bodies]


def split_commands(line):
    """[(simple command, separator after it)] split on unquoted ; && || | & and newlines; quoted text stays in one piece.

    The separator is one of ";", "\\n", "|", "||", "&", "&&" or "" (end of the line)."""
    parts, buf = [], []
    quote = None
    i, n = 0, len(line)

    def cut(sep):
        parts.append(("".join(buf), sep))
        del buf[:]

    while i < n:
        c = line[i]
        if quote == "'":
            buf.append(c)
            if c == "'":
                quote = None
        elif quote == '"':
            buf.append(c)
            if c == "\\" and i + 1 < n:
                buf.append(line[i + 1])
                i += 1
            elif c == '"':
                quote = None
        elif c == "\\" and i + 1 < n:
            buf.append(c)
            buf.append(line[i + 1])
            i += 1
        elif c in "'\"":
            quote = c
            buf.append(c)
        elif c in ";\n":
            cut(c)
        elif c == "|":
            if i + 1 < n and line[i + 1] == "|":
                i += 1
                cut("||")
            else:
                cut("|")
        elif c == "&":
            prev = line[i - 1] if i else ""
            nxt = line[i + 1] if i + 1 < n else ""
            if prev in "<>" or nxt == ">":   # 2>&1, &>file
                buf.append(c)
            elif nxt == "&":
                i += 1
                cut("&&")
            else:
                cut("&")
        else:
            buf.append(c)
        i += 1
    cut("")
    out = []
    for text, sep in parts:
        if text.strip():
            out.append((text.strip(), sep))
        elif out and sep == "|" and out[-1][1] != "|":
            out[-1] = (out[-1][0], "|")   # `a |&`: the pipe goes on across the empty piece
    return out


REDIRECT_RE = re.compile(r"^(?:(?:[0-9]+|\{[A-Za-z_][A-Za-z0-9_]*\})?(<<<|<<-?|<>|<&|<|>>|>&|>\||>)|(&>>?))(.*)$", re.S)


def split_redirections(tokens):
    """(tokens without redirections, redirection targets): `2>/dev/null`, `>> log`, `< file`, `&>x`, `2>&1`.

    The targets are returned because a printer must still be checked against a secret file named there."""
    words, targets = [], []
    i = 0
    while i < len(tokens):
        m = REDIRECT_RE.match(tokens[i])
        if not m:
            words.append(tokens[i])
        elif m.group(3):
            targets.append(m.group(3))
        elif i + 1 < len(tokens):
            targets.append(tokens[i + 1])
            i += 1
        i += 1
    return words, targets


def tokenize(segment):
    try:
        return shlex.split(segment)
    except ValueError:
        return segment.split()


ENV_SHORT_WITH_VALUE = "uCS"   # -u NAME, -C DIR, -S STRING: each one takes a value, glued or in the next word
ENV_LONG_WITH_VALUE = ("--unset", "--chdir", "--split-string")


def env_parse(args):
    """(index, directory) for `env [-i] [-u NAME] [-C DIR] [NAME=value ...] command`.

    index is where the command starts in `args`: None when env runs no command (it prints the
    environment), -1 when we cannot tell where it runs it (`-S` splits a string). directory is the
    last `-C DIR` / `--chdir=DIR` given, as written, or None."""
    i, directory = 0, None
    while i < len(args):
        arg = args[i]
        if arg == "--":
            i += 1
            break
        if arg.startswith("--"):
            name, eq, value = arg.partition("=")
            if name in ENV_LONG_WITH_VALUE:
                if not eq:
                    value = args[i + 1] if i + 1 < len(args) else ""
                    i += 1
                if name == "--split-string":
                    return -1, directory
                if name == "--chdir":
                    directory = value
            i += 1
        elif arg.startswith("-") and arg != "-":
            letters = arg[1:]
            k = next((n for n, ch in enumerate(letters) if ch in ENV_SHORT_WITH_VALUE), None)
            if k is None:
                i += 1
                continue
            value = letters[k + 1:]
            if not value:
                value = args[i + 1] if i + 1 < len(args) else ""
                i += 1
            if letters[k] == "S":
                return -1, directory
            if letters[k] == "C":
                directory = value
            i += 1
        elif ASSIGNMENT_RE.match(arg):
            i += 1
        else:
            break
    return (i if i < len(args) else None), directory


def env_command(args):
    """Index in `args` of the command that `env ... command` runs (see env_parse)."""
    return env_parse(args)[0]


def strip_prefix(tokens, base=None):
    """(tokens, directory): drop leading VAR=value assignments and the wrappers command/sudo/time/nohup/env.

    directory is `base` unless an `env -C` moved the command elsewhere; None when it cannot be known."""
    i = 0
    directory = base
    while i < len(tokens):
        if tokens[i] == "env" or os.path.basename(tokens[i]) == "env":
            index, chdir = env_parse(tokens[i + 1:])
            if index is None:
                break   # `env` alone prints the environment: decide_simple denies it
            if index < 0:
                return [], directory
            if chdir is not None:
                if directory and not any(ch in chdir for ch in "$`*?"):
                    directory = os.path.normpath(os.path.join(directory, os.path.expanduser(chdir)))
                else:
                    directory = None
            i += 1 + index
        elif tokens[i] == "nice":
            i += 1
            if i < len(tokens) and tokens[i] == "-n" and i + 1 < len(tokens):
                i += 2
            elif i < len(tokens) and NICE_OPTION_RE.match(tokens[i]):
                i += 1
        elif ASSIGNMENT_RE.match(tokens[i]) or tokens[i] in WRAPPERS:
            i += 1
        else:
            break
    return tokens[i:], directory


# ---------------------------------------------------------------------------------------------
# git
# ---------------------------------------------------------------------------------------------

def run_git(directory, *args):
    """stdout of `git -C directory args`, or None when it fails or the directory is unusable."""
    if not directory or not os.path.isdir(directory):
        return None
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")}
    env["GIT_OPTIONAL_LOCKS"] = "0"
    try:
        res = subprocess.run(["git", "-C", directory] + list(args), stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, env=env, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if res.returncode != 0:
        return None
    return res.stdout.decode("utf-8", "replace").strip()


def current_branch(directory):
    """Branch name, or None (not a repository, detached HEAD, cannot tell)."""
    return run_git(directory, "symbolic-ref", "--short", "-q", "HEAD") or None


def manifest_default_branch(top, root):
    """Branch of the repos.json entry whose clone is `top`; None when `top` is not one."""
    try:
        with open(os.path.join(root, "repos.json"), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get("repos"), list):
        return None
    normalize = _check().normalize_rel  # the same normalization as scripts/check.py
    base = normalize(data.get("root")) or "repos"
    for repo in data["repos"]:
        if not isinstance(repo, dict):
            continue
        rel = normalize(repo.get("path") or repo.get("name"))
        if rel is None:
            continue
        clone = os.path.realpath(os.path.join(root, base, rel))
        if clone == top:
            branch = repo.get("branch")
            return branch if isinstance(branch, str) and branch else "main"
    return None


def default_branch(directory, root, current):
    top = run_git(directory, "rev-parse", "--show-toplevel")
    if not top:
        return None
    from_manifest = manifest_default_branch(os.path.realpath(top), os.path.realpath(root))
    if from_manifest:
        return from_manifest
    head = run_git(directory, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
    if head:
        return head[len("origin/"):] if head.startswith("origin/") else head
    return current if current in ("main", "master") else None


def short_flags(arg):
    """Letters of a short-option cluster such as -fu; stops at -o, whose rest is a value."""
    if not arg.startswith("-") or arg.startswith("--") or len(arg) < 2:
        return ""
    letters = arg[1:]
    cut = letters.find("o")
    return letters if cut < 0 else letters[:cut + 1]


def parse_git(tokens, cur):
    """(effective directory, subcommand, args) of a `git ...` simple command; directory None = unknown."""
    directory = cur
    i = 1
    while i < len(tokens) and tokens[i].startswith("-"):
        tok = tokens[i]
        if tok == "-C" and i + 1 < len(tokens):
            target = os.path.expanduser(tokens[i + 1])
            directory = os.path.normpath(os.path.join(directory, target)) if directory else None
            i += 2
        elif tok == "-c" and i + 1 < len(tokens):
            i += 2
        elif tok.startswith(("--git-dir", "--work-tree")):
            directory = None
            i += 2 if "=" not in tok else 1
        elif tok in ("--namespace", "--super-prefix", "--exec-path") and i + 1 < len(tokens):
            i += 2
        else:
            i += 1
    if i >= len(tokens):
        return directory, None, []
    return directory, tokens[i], tokens[i + 1:]


def checkout_hint(directory, root):
    try:
        rel = os.path.relpath(os.path.realpath(directory), os.path.realpath(root))
    except ValueError:
        rel = directory
    if rel.startswith(".."):
        rel = directory
    if rel == ".":
        return "git checkout -b <type>/<short-slug>"
    return "git -C %s checkout -b <type>/<short-slug>" % shlex.quote(rel)


def analyse_push(args):
    """(forced, deleting, refspecs) of the arguments after `git push`."""
    forced = deleting = False
    positional = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--":
            positional.extend(args[i + 1:])
            break
        if arg.startswith("--"):
            name = arg.split("=", 1)[0]
            if name in ("--force", "--force-with-lease", "--force-if-includes"):
                forced = True
            elif name == "--delete":
                deleting = True
            if name in PUSH_OPTIONS_WITH_VALUE and "=" not in arg:
                i += 1
        elif arg.startswith("-") and len(arg) > 1:
            flags = short_flags(arg)
            forced = forced or "f" in flags
            deleting = deleting or "d" in flags
            if arg == "-o":
                i += 1
        else:
            positional.append(arg)
        i += 1
    return forced, deleting, positional[1:]   # the first positional is the remote


def destination(refspec, current):
    dest = refspec.lstrip("+").rsplit(":", 1)[-1] if ":" in refspec.lstrip("+") else refspec.lstrip("+")
    if dest in ("HEAD", "@"):
        dest = current
    return dest[len("refs/heads/"):] if dest and dest.startswith("refs/heads/") else dest


COMMIT_ISH_RE = re.compile(r"^(@|HEAD.*|.*[~^:]|.*@\{.*|[0-9a-f]{7,40})$")
# options that take a value in the next argument (without `=`), for `git checkout|switch`
SWITCH_VALUE_OPTIONS = ("--conflict", "--orphan", "--unified", "--inter-hunk-context", "--pathspec-from-file")
# options after which the arguments are paths to restore, not a branch to switch to
RESTORE_OPTIONS = ("--patch", "--pathspec-from-file", "--ours", "--theirs")


def repo_key(directory):
    """Identity of the repository that `directory` belongs to (its top level), or None."""
    top = run_git(directory, "rev-parse", "--show-toplevel")
    return os.path.realpath(top) if top else None


def is_local_branch(directory, name):
    return run_git(directory, "show-ref", "--verify", "--quiet", "refs/heads/" + name) is not None


def branch_after_switch(sub, args, directory):
    """The branch a `git checkout|switch args` leaves us on: a name, UNKNOWN, or None (no change we can tell)."""
    letters_creating = "bB" if sub == "checkout" else "cC"
    long_creating = () if sub == "checkout" else ("--create", "--force-create")
    i = 0
    while i < len(args):   # `-b new`, `-bnew`, `-qb new`, `--create new`, `--create=new`
        arg = args[i]
        if arg == "--":
            break
        if arg.startswith("--"):
            name, eq, value = arg.partition("=")
            if name in long_creating:
                return value if eq else (args[i + 1] if i + 1 < len(args) else UNKNOWN)
            if name in SWITCH_VALUE_OPTIONS and not eq:
                i += 1
        elif arg.startswith("-") and len(arg) > 1:
            for pos, letter in enumerate(arg[1:], 1):
                if letter in letters_creating:
                    return arg[pos + 1:] or (args[i + 1] if i + 1 < len(args) else UNKNOWN)
                if letter == "U":
                    break
        i += 1
    explicit_paths = False
    if "--" in args:
        cut = args.index("--")
        if sub == "checkout" and args[cut + 1:]:
            return None   # `git checkout [<tree-ish>] -- <paths>` restores files; the branch stays
        args, explicit_paths = args[:cut], True   # `git checkout <branch> --` still switches
    positional, tracking, detach, restoring = [], False, False, False
    i = 0
    while i < len(args):
        arg = args[i]
        if arg.startswith("--"):
            name, eq, _ = arg.partition("=")
            tracking = tracking or name == "--track"
            detach = detach or name in ("--detach", "--orphan")
            restoring = restoring or name in RESTORE_OPTIONS
            if name in SWITCH_VALUE_OPTIONS and not eq:
                i += 1
        elif arg == "-" or not arg.startswith("-"):
            positional.append(arg)
        else:
            for letter in arg[1:]:
                tracking = tracking or letter == "t"
                detach = detach or letter == "d"
                restoring = restoring or letter == "p"
                if letter == "U":
                    break
        i += 1
    if restoring:
        return None   # -p, --pathspec-from-file, --ours, --theirs work on files
    if detach:
        return UNKNOWN
    if not positional:
        return None
    if positional[0] == "-":
        return UNKNOWN   # the previous branch
    if sub == "checkout" and len(positional) > 1:
        return None      # `git checkout <tree-ish> <paths>`
    name = positional[0]
    if tracking:
        remote, _, branch = name.partition("/")
        return branch if branch else UNKNOWN
    if name != "." and is_local_branch(directory, name):
        return name      # git prefers the branch when a path has the same name
    if name == "." or COMMIT_ISH_RE.match(name):
        return None
    if not explicit_paths and directory and os.path.exists(os.path.join(directory, os.path.expanduser(name))):
        return None      # a path, not a branch
    return name


def is_fresh_repository(directory):
    """True for a repository with no commit yet and no `origin`: there is nothing to protect."""
    if run_git(directory, "rev-parse", "--verify", "-q", "HEAD") is not None:
        return False
    remotes = run_git(directory, "remote")
    return remotes is not None and "origin" not in remotes.split()


def decide_git(sub, args, directory, root, overrides):
    """Decision for one `git <sub> args` command; `overrides` maps repositories to a branch set earlier in the line."""
    key = repo_key(directory) if sub in ("checkout", "switch", "commit", "push") else None

    if sub == "branch":
        for arg in args:
            if arg == "--delete" or "d" in short_flags(arg).replace("D", "d"):
                return "ask", "deletes a branch: confirm with the user."
        return "allow", ""

    if sub in ("checkout", "switch"):
        new = branch_after_switch(sub, args, directory)
        if new is not None and key:
            overrides[key] = new
        return "allow", ""

    if sub not in ("commit", "push"):
        return "allow", ""

    forced = deleting = False
    refspecs = []
    tags_only = False
    if sub == "push":
        forced, deleting, refspecs = analyse_push(args)
        tags_only = "--tags" in args and not refspecs
    verdicts = []
    if sub == "push":
        if forced or any(r.startswith("+") for r in refspecs):
            verdicts.append(("ask", "force-push rewrites remote history: confirm with the user."))
        if deleting or any(r.startswith(":") and len(r) > 1 for r in refspecs):
            verdicts.append(("ask", "deletes a remote branch: confirm with the user."))
        if deleting or tags_only:
            return max_decision(verdicts)

    branch = overrides.get(key) if key in overrides else current_branch(directory)
    if branch is None or branch is UNKNOWN:
        return max_decision(verdicts)
    default = default_branch(directory, root, branch)
    if default is None or is_fresh_repository(directory):
        return max_decision(verdicts)

    if sub == "commit":
        if branch == default:
            verdicts.append(("deny", "never commit directly to the default branch (%s). Create a branch first with "
                                     "`%s`, then commit." % (default, checkout_hint(directory, root))))
    else:
        pushed = [r for r in refspecs if not (r.startswith(":") and len(r) > 1)]
        if refspecs and not pushed:   # only deletions, already asked about
            return max_decision(verdicts)
        targets = [destination(r, branch) for r in pushed] or [branch]
        if default in targets:
            verdicts.append(("deny", "never push directly to the default branch (%s). Push a feature branch "
                                     "(`git push -u origin HEAD` from a branch created with `%s`) and open a PR instead."
                             % (default, checkout_hint(directory, root))))
    return max_decision(verdicts)


def max_decision(verdicts):
    best = ("allow", "")
    for verdict in verdicts:
        if SEVERITY[verdict[0]] > SEVERITY[best[0]]:
            best = verdict
    return best


# ---------------------------------------------------------------------------------------------
# shell commands
# ---------------------------------------------------------------------------------------------

def expand(arg, base):
    """The argument itself, plus what it expands to when it is a glob that matches files."""
    out = [arg]
    if any(ch in arg for ch in "*?["):
        try:
            out.extend(glob.glob(os.path.join(base, os.path.expanduser(arg))))
        except OSError:
            pass
    return out


GH_FLAGS_WITH_VALUE = ("-R", "--repo", "--hostname")
SHELLS = ("bash", "sh", "zsh", "dash")
MAX_DEPTH = 3   # nested `bash -c '...'`


KEYWORDS = ("do", "then", "else", "elif", "if", "while", "until", "!", "{")   # each one introduces a command
GROUP_OPEN, GROUP_CLOSE = "\ue002", "\ue003"   # a subshell parenthesis found by mark_groups


def strip_grouping(tokens):
    """Drop the keywords that introduce a command (`do`, `then`, `else`, `{`, ...) and a closing `}`.

    The parentheses of a subshell are not here: mark_groups finds them in the text."""
    tokens = list(tokens)
    while tokens and tokens[0] in KEYWORDS:
        tokens.pop(0)
    while tokens and tokens[-1] == "}":
        tokens.pop()
    return tokens


def _skip_group(text, i):
    """Index after the `( ... )` that starts at text[i], quotes and nested groups included; the end when it never closes."""
    depth, j, n = 0, i, len(text)
    while j < n:
        c = text[j]
        if c == "\\":
            j += 1
        elif c == "'":
            j = text.find("'", j + 1)
            if j < 0:
                return n
        elif c == '"':
            j += 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j + 1
        j += 1
    return n


def mark_groups(text):
    """`text` with each grouping parenthesis replaced by GROUP_OPEN / GROUP_CLOSE.

    A grouping parenthesis opens or closes a subshell: an unquoted `(` where a command starts, and the
    unquoted `)` that matches it. Quotes, `$( ... )`, backticks, `<( ... )`, `(( ... ))` and the `)` of
    a `case` pattern are left as they are."""
    out, depth = [], 0
    command = True   # a command starts here
    word = []
    i, n = 0, len(text)

    def end_word():
        nonlocal command
        if word:
            command = "".join(word) in KEYWORDS or "".join(word) in WRAPPERS   # `time (cd x; ...)`
            del word[:]

    while i < n:
        c = text[i]
        if c in " \t":
            end_word()
        elif c in ";\n&|":
            end_word()
            command = True
        elif c == "\\" and i + 1 < n:
            word.append(text[i:i + 2])
            out.append(text[i:i + 2])
            i += 2
            continue
        elif c in "'\"":
            if c == "'":
                end = text.find("'", i + 1)
                end = n if end < 0 else end + 1
            else:
                end = i + 1
                while end < n and text[end] != '"':
                    end += 2 if text[end] == "\\" else 1
                end = min(end + 1, n)
            word.append("x")
            out.append(text[i:end])
            i = end
            continue
        elif c == "`":
            end = text.find("`", i + 1)
            end = n if end < 0 else end + 1
            word.append("x")
            out.append(text[i:end])
            i = end
            continue
        elif c == "#" and not word:
            end = text.find("\n", i)
            end = n if end < 0 else end
            out.append(text[i:end])
            i = end
            continue
        elif c in "$<>" and text.startswith("(", i + 1):
            end = _skip_group(text, i + 1)
            word.append("x")
            out.append(text[i:end])
            i = end
            continue
        elif c == "(" and command and text.startswith("((", i):
            end = _skip_arithmetic(text, i)
            word.append("x")
            out.append(text[i:end])
            i = end
            continue
        elif c == "(" and command:
            out.append(GROUP_OPEN)
            depth += 1
            i += 1
            continue
        elif c == ")" and depth:
            end_word()
            out.append(GROUP_CLOSE)
            depth -= 1
            command = False
            i += 1
            continue
        else:
            word.append(c)
        out.append(c)
        i += 1
    return "".join(out)


def gh_words(args):
    """The first two words of a `gh` command that are not flags (nor the values of -R/--repo/--hostname)."""
    words, i = [], 0
    while i < len(args) and len(words) < 2:
        arg = args[i]
        if arg.startswith("-") and arg != "-":
            if arg in GH_FLAGS_WITH_VALUE:
                i += 1
        else:
            words.append(arg)
        i += 1
    return words


SHELL_FLAGS_WITH_VALUE = ("-o", "+o", "-O", "+O", "--rcfile", "--init-file")


def first_operand(args, j):
    """Index of the first word of args[j:] that is not an option (`--` ends the options)."""
    while j < len(args):
        arg = args[j]
        if arg == "--":
            return j + 1
        if arg[:1] not in ("-", "+") or arg in ("-", "+"):
            return j
        if arg.startswith("--"):
            j += 2 if arg in SHELL_FLAGS_WITH_VALUE else 1
        else:
            j += 1 + sum(1 for letter in arg[1:] if letter in "oO")
    return j


def parse_shell_args(args):
    """How a `bash ...` invocation gets its commands: ("c", text or None), ("script", None) or ("stdin", None).

    `-c` is looked for among the flags, combined ones included (`-lc`, `-ec`); the value of `-o`, `+o`,
    `-O`, `+O` and `--rcfile` is skipped. The string of `-c` is the first word that is not an option, so
    `--` is skipped. With `-s` the shell reads stdin and the words left are positional parameters."""
    i = 0
    reads_stdin = False
    while i < len(args):
        arg = args[i]
        if arg == "--":
            return ("script", None) if i + 1 < len(args) and not reads_stdin else ("stdin", None)
        if arg[:1] not in ("-", "+") or arg in ("-", "+"):
            return ("script", None) if arg not in ("-", "+") and not reads_stdin else ("stdin", None)
        if arg.startswith("--"):
            i += 2 if arg in SHELL_FLAGS_WITH_VALUE else 1
            continue
        valued = sum(1 for letter in arg[1:] if letter in "oO")
        if arg[0] == "-" and "c" in arg[1:]:
            j = i + 1 + valued
            j = first_operand(args, j)
            return "c", (args[j] if j < len(args) else None)
        reads_stdin = reads_stdin or (arg[0] == "-" and "s" in arg[1:])
        i += 1 + valued
    return "stdin", None


def shell_command_string(args):
    """The literal string after `-c` of `bash -c '...'`; None when absent or when it is built at run time."""
    kind, text = parse_shell_args(args)
    if kind == "c" and text and "$" not in text and "`" not in text:
        return text
    return None


def unmark(segment):
    return segment.replace(GROUP_OPEN, " ").replace(GROUP_CLOSE, " ")


def runs_stdin_script(commands, index):
    """True when the heredoc of commands[index] feeds a shell: the command itself, or the end of its pipeline."""
    last = index
    while commands[last][1] == "|" and last + 1 < len(commands):
        last += 1
    for k in {index, last}:
        tokens = strip_prefix(strip_grouping(split_redirections(tokenize(HEREDOC_MARK_RE.sub(" ", unmark(commands[k][0]))))[0]))[0]
        if tokens and os.path.basename(tokens[0]) in SHELLS and parse_shell_args(tokens[1:])[0] == "stdin":
            return True
    return False


def decide_simple(tokens, cur, cwd, root, overrides, depth=0):
    """(decision, new current directory) for one simple command."""
    tokens, targets = split_redirections(strip_grouping(tokens))
    # `do env git push`: keywords and wrappers can alternate; `env -C dir` runs the command in dir
    tokens, where = strip_prefix(strip_grouping(tokens), cur or None)
    if not tokens:
        return ("allow", ""), cur
    word, args = tokens[0], tokens[1:]
    name = os.path.basename(word)
    base = cur or cwd
    if where != (cur or None):   # the directory of this command only; the shell's own directory is `cur`
        inner, _ = decide_simple(tokens, where, cwd, root, overrides, depth)
        return inner, cur

    if name == "cd":
        target = [a for a in args if not a.startswith("-")]
        if len(args) == 1 and len(target) == 1 and not any(ch in target[0] for ch in "$`*?"):
            return ("allow", ""), os.path.normpath(os.path.join(base, os.path.expanduser(target[0])))
        return ("allow", ""), None

    if name == "git":
        directory, sub, rest = parse_git(tokens, cur if cur else None)
        if sub is None:
            return ("allow", ""), cur
        return decide_git(sub, rest, directory, root, overrides), cur

    if name == "gh":
        if gh_words(args) == ["pr", "merge"] and not any(a in ("--help", "-h") for a in args):
            return ("ask", "merging a PR is the user's decision: confirm with the user."), cur
        return ("allow", ""), cur

    if name in SHELLS and depth < MAX_DEPTH:
        text = shell_command_string(args)
        if text:
            # a subshell keeps its own directory, but a checkout changes the repository: the branches are shared
            inner, _ = decide_line(text, cwd, root, cur, overrides, depth + 1)
            return inner, cur

    if (name == "printenv" and not args) or (name == "env" and env_command(args) is None
                                             and not any(a in ("--help", "--version") for a in args)):
        return ("deny", ENV_DUMP_REASON), cur
    if (word == "export" and args in ([], ["-p"])) or (word == "declare" and args == ["-x"]) or (word == "set" and not args):
        return ("deny", ENV_DUMP_REASON), cur

    if name in PRINTERS:
        for arg in args + targets:
            if arg.startswith("-"):
                continue
            for path in expand(arg, base):
                if is_secret_path(path, base, root, include_dir=True):
                    return ("deny", SECRET_REASON), cur
    return ("allow", ""), cur


def decide_line(command, cwd, root, cur, overrides, depth=0):
    """(decision, directory after the line) for a command line run in `cur`.

    `overrides` maps each repository to the branch an earlier checkout of the line left it on; it is shared
    with subshells, because a checkout outlives them. The directory is not: `(cd x; ...)` leaves it behind."""
    verdicts = []
    scopes = []   # the directory saved at each `(`
    text, bodies = extract_heredocs(command)
    commands = split_commands(mark_groups(text))
    for index, (segment, _) in enumerate(commands):
        marks = [int(m) for m in HEREDOC_MARK_RE.findall(segment)]
        scopes.extend([cur] * segment.count(GROUP_OPEN))
        tokens = tokenize(HEREDOC_MARK_RE.sub(" ", unmark(segment)))
        verdict, cur = decide_simple(tokens, cur, cwd, root, overrides, depth)
        verdicts.append(verdict)
        for _ in range(segment.count(GROUP_CLOSE)):
            if scopes:
                cur = scopes.pop()
        if marks and depth < MAX_DEPTH and runs_stdin_script(commands, index):
            for mark in marks:   # the body of a heredoc that a shell reads is a command line
                body, quoted = bodies[mark]
                if quoted or ("$" not in body and "`" not in body):
                    verdicts.append(decide_line(body, cwd, root, cur, overrides, depth + 1)[0])
    return max_decision(verdicts), cur


def decide_shell(command, cwd, root):
    if isinstance(command, list):
        command = " ".join(shlex.quote(str(c)) for c in command)
    if not isinstance(command, str):
        return "allow", ""
    return decide_line(command, cwd, root, cwd, {})[0]


# ---------------------------------------------------------------------------------------------
# entry point of the decision
# ---------------------------------------------------------------------------------------------

def decide(tool, tool_input, cwd, root):
    """("allow" | "ask" | "deny", reason). Never raises: an internal error allows the call."""
    try:
        name = str(tool or "").lower()
        if not isinstance(tool_input, dict):
            return "allow", ""
        cwd = os.path.abspath(cwd or os.getcwd())
        root = os.path.abspath(root or DEFAULT_ROOT)
        if name in FILE_TOOLS or name in PATCH_TOOLS:
            return decide_file_tool(name, tool_input, cwd, root)
        if name in SHELL_TOOLS:
            command = tool_input.get("command", tool_input.get("cmd"))
            return decide_shell(command, cwd, root)
        return "allow", ""
    except Exception as exc:  # a broken guard must never block the agent
        print("guard: internal error, allowing the call (%s: %s)" % (type(exc).__name__, exc), file=sys.stderr)
        return "allow", ""


# ---------------------------------------------------------------------------------------------
# adapters
# ---------------------------------------------------------------------------------------------

def block_reason(decision, reason):
    """Agents that cannot ask the user (Codex, OpenCode) get a block that says to ask."""
    if decision == "ask":
        return "%s Blocked: %s." % (reason, ASK_HINT)
    return reason


def respond(agent, decision, reason):
    """(stdout text, exit code) in the format of `agent`."""
    if agent == "claude":
        if decision == "allow":
            return "", 0
        return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                                  "permissionDecisionReason": reason}}), 0
    if agent == "codex":
        if decision == "allow":
            return "", 0
        return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                  "permissionDecisionReason": block_reason(decision, reason)}}), 0
    # opencode: the plugin throws the reason on anything but "allow"
    if decision == "allow":
        return json.dumps({"decision": "allow"}), 0
    return json.dumps({"decision": "deny", "reason": block_reason(decision, reason)}), 0


def read_call(agent, payload, default_cwd):
    """(tool, tool_input, cwd) from the payload an agent sends."""
    if agent == "opencode":
        return payload.get("tool"), payload.get("args", payload.get("tool_input")), payload.get("cwd") or default_cwd
    return payload.get("tool_name"), payload.get("tool_input"), payload.get("cwd") or default_cwd


def run_adapter(agent, stdin, stdout):
    try:
        payload = json.loads(stdin.read() or "{}")
        tool, tool_input, cwd = read_call(agent, payload if isinstance(payload, dict) else {}, os.getcwd())
        decision, reason = decide(tool, tool_input, cwd, DEFAULT_ROOT)
        text, code = respond(agent, decision, reason)
    except Exception as exc:
        print("guard: internal error, allowing the call (%s: %s)" % (type(exc).__name__, exc), file=sys.stderr)
        text, code = respond(agent, "allow", "")
    if text:
        stdout.write(text + "\n")
    return code


def main(argv=None):
    parser = argparse.ArgumentParser(description="Decide whether an agent tool call is allowed.")
    parser.add_argument("--agent", choices=("claude", "codex", "opencode"),
                        help="read one tool call as JSON on stdin and answer in this agent's format")
    parser.add_argument("--explain", metavar="COMMAND", help="print the decision for a shell command run in the current directory")
    args = parser.parse_args(argv)
    if args.explain is not None:
        decision, reason = decide("Bash", {"command": args.explain}, os.getcwd(), DEFAULT_ROOT)
        print("%s: %s" % (decision, reason) if reason else decision)
        return 0
    if args.agent:
        return run_adapter(args.agent, sys.stdin, sys.stdout)
    parser.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
