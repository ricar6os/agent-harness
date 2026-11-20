"""Tests for scripts/guard.py: the decision function, table-driven, and the three agent adapters."""
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
GUARD = REPO / "scripts" / "guard.py"
_spec = importlib.util.spec_from_file_location("guard", str(GUARD))
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


def run(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-C", str(cwd)] + list(args),
                   check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def make_repo(path, branch):
    path.mkdir(parents=True, exist_ok=True)
    run(path, "init", "-q", "-b", branch)
    (path / "README.md").write_text("x\n")
    run(path, "add", "-A")
    run(path, "commit", "-q", "-m", "init")


class Fixture(unittest.TestCase):
    """Workspace `ws` (meta root, on main) with clones whose manifest branches differ, plus loose repos."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="guard-test-")
        tmp = Path(cls.tmp)
        ws = tmp / "ws"
        make_repo(ws, "main")
        (ws / "repos.json").write_text(json.dumps({"org": "acme", "root": "repos", "repos": [
            {"name": "api", "url": "u", "branch": "develop"},
            {"name": "api-feat", "url": "u", "branch": "develop"},
            {"name": "web", "url": "u"},
            {"name": "det", "url": "u"},
        ]}))
        (ws / "env" / "api").mkdir(parents=True)
        (ws / "env" / "README.md").write_text("env\n")
        (ws / "env" / "api" / ".gitkeep").write_text("")
        (ws / "env" / "api" / ".env").write_text("TOKEN=secret\n")
        (ws / "env" / "api" / "secrets.txt").write_text("TOKEN=secret\n")
        make_repo(ws / "repos" / "api", "develop")
        make_repo(ws / "repos" / "api-feat", "develop")
        run(ws / "repos" / "api-feat", "checkout", "-q", "-b", "feat/x")
        make_repo(ws / "repos" / "web", "main")
        run(ws / "repos" / "web", "checkout", "-q", "-b", "feat/x")
        (ws / "repos" / "web" / "main").mkdir()   # a directory named like the branch `main`
        make_repo(ws / "repos" / "det", "main")
        run(ws / "repos" / "det", "checkout", "-q", "--detach")
        os.symlink("../../env/api/.env", str(ws / "repos" / "api" / ".env"))
        os.symlink("../../env/api/secrets.txt", str(ws / "repos" / "api" / "link"))
        ws2 = tmp / "ws2"   # a second meta root, on a feature branch
        make_repo(ws2, "main")
        run(ws2, "checkout", "-q", "-b", "feat/y")
        (ws2 / "repos.json").write_text(json.dumps({"org": "acme", "repos": []}))
        ext = tmp / "ext"   # outside every manifest: default branch comes from origin/HEAD
        make_repo(ext, "trunk")
        run(ext, "update-ref", "refs/remotes/origin/trunk", "HEAD")
        run(ext, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
        legacy = tmp / "legacy"  # no origin: master is recognised by its name
        make_repo(legacy, "master")
        (tmp / "plain").mkdir()
        (tmp / "fresh").mkdir()      # a new repository: unborn HEAD, no origin
        run(tmp / "fresh", "init", "-q", "-b", "main")
        (tmp / "freshorigin").mkdir()   # unborn HEAD, but a remote exists
        run(tmp / "freshorigin", "init", "-q", "-b", "main")
        run(tmp / "freshorigin", "remote", "add", "origin", "https://example.com/x.git")
        cls.paths = {
            "fresh": str(tmp / "fresh"), "freshorigin": str(tmp / "freshorigin"),
            "root": str(ws), "root2": str(ws2), "api": str(ws / "repos" / "api"),
            "apif": str(ws / "repos" / "api-feat"), "web": str(ws / "repos" / "web"),
            "det": str(ws / "repos" / "det"), "ext": str(ext), "legacy": str(legacy),
            "plain": str(tmp / "plain"),
        }

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, True)

    def decide(self, tool, tool_input, where="root", root=None):
        cwd = self.paths.get(where, where)
        return guard.decide(tool, tool_input, cwd, root or self.paths["root"])


# (cwd key, command, decision, reason fragment)
SHELL_CASES = [
    # ask: force-push
    ("apif", "git push --force origin feat/x", "ask", "force-push"),
    ("apif", "git push -f origin feat/x", "ask", "force-push"),
    ("apif", "git push -fu origin HEAD", "ask", "force-push"),
    ("apif", "git push -uf origin HEAD", "ask", "force-push"),
    ("apif", "git push --force-with-lease", "ask", "force-push"),
    ("apif", "git push --force-with-lease=feat/x origin feat/x", "ask", "force-push"),
    ("apif", "git push --force-if-includes origin feat/x", "ask", "force-push"),
    ("apif", "git push origin +feat/x", "ask", "force-push"),
    ("apif", "git push origin +HEAD:feat/x", "ask", "force-push"),
    # ask: remote branch deletion
    ("apif", "git push --delete origin feat/x", "ask", "deletes a remote branch"),
    ("apif", "git push -d origin feat/x", "ask", "deletes a remote branch"),
    ("apif", "git push origin :feat/x", "ask", "deletes a remote branch"),
    ("api", "git push origin :develop", "ask", "deletes a remote branch"),      # a deletion, not a push to develop
    ("api", "git push --delete origin develop", "ask", "deletes a remote branch"),
    # ask: local branch deletion and PR merge
    ("apif", "git branch -d old", "ask", "deletes a branch"),
    ("apif", "git branch -D old", "ask", "deletes a branch"),
    ("apif", "git branch --delete old", "ask", "deletes a branch"),
    ("apif", "gh pr merge 12", "ask", "merging a PR"),
    ("apif", "gh pr merge --squash --auto", "ask", "merging a PR"),
    # deny: commit on the default branch
    ("root", "git commit -m x", "deny", "default branch (main)"),
    ("api", "git commit -m x", "deny", "default branch (develop)"),
    ("api", "git commit --amend", "deny", "git -C repos/api checkout -b <type>/<short-slug>"),
    ("root", "git -C repos/api commit -m x", "deny", "git -C repos/api checkout -b <type>/<short-slug>"),
    ("apif", "git -C ../api commit -m x", "deny", "git -C repos/api checkout -b"),
    ("root", "cd repos/api && git commit -m x", "deny", "git -C repos/api checkout -b"),
    ("root", "cd repos/api; git commit -m x", "deny", "default branch (develop)"),
    ("web", "git -C ../../ commit -m x", "deny", "default branch (main)"),
    ("ext", "git commit -m x", "deny", "default branch (trunk)"),
    ("legacy", "git commit -m x", "deny", "default branch (master)"),
    ("root", "git status && FOO=1 git commit -m x", "deny", "default branch"),
    ("root", "sudo -n git commit -m x", "allow", ""),      # sudo flags are not followed: nothing certain
    ("root", "command git commit -m x", "deny", "default branch"),
    ("root", "nice git commit -m x", "deny", "default branch"),
    ("root", "nice -n 5 git commit -m x", "deny", "default branch"),
    ("root", "nice -n -5 git commit -m x", "deny", "default branch"),
    ("root", "nice -5 git commit -m x", "deny", "default branch"),
    ("root", "nice --adjustment=5 git commit -m x", "deny", "default branch"),
    ("root", "nice make test", "allow", ""),
    ("root", "nice", "allow", ""),
    # deny: push to the default branch
    ("api", "git push", "deny", "default branch (develop)"),
    ("api", "git push -u origin HEAD", "deny", "open a PR"),
    ("api", "git push origin develop", "deny", "default branch (develop)"),
    ("apif", "git push origin HEAD:develop", "deny", "default branch (develop)"),
    ("apif", "git push origin x:develop", "deny", "default branch (develop)"),
    ("apif", "git push origin feat/x:refs/heads/develop", "deny", "default branch (develop)"),
    ("web", "git push origin HEAD:main", "deny", "default branch (main)"),
    ("web", "git push origin main", "deny", "default branch (main)"),
    ("root", "git push", "deny", "default branch (main)"),
    ("apif", "git push --force origin HEAD:develop", "deny", "default branch"),   # deny wins over ask
    # deny: printing secret files
    ("root", "cat env/api/.env", "deny", "secret values stay out of the conversation"),
    ("api", "cat ../../env/api/.env", "deny", "read the `.example` template"),
    ("api", "head -n1 .env", "deny", "secret values"),
    ("api", "cat link", "deny", "secret values"),                    # symlink to env/api/secrets.txt
    ("root", "cat env/api/secrets.txt", "deny", "secret values"),
    ("root", "grep TOKEN env/api/secrets.txt", "deny", "secret values"),
    ("root", "grep -r TOKEN env/", "deny", "secret values"),
    ("web", "cat .env.local", "deny", "secret values"),
    ("web", "tail -f .env.production", "deny", "secret values"),
    ("web", "less .env", "deny", "secret values"),
    ("web", "cat -n .env", "deny", "secret values"),
    ("web", "cat < .env", "deny", "secret values"),
    ("web", "cat <.env", "deny", "secret values"),
    ("web", "sed -n 1p .env", "deny", "secret values"),
    ("web", "awk '{print}' .env", "deny", "secret values"),
    ("api", "cat .env*", "deny", "secret values"),                   # the glob matches the linked .env
    ("web", "jq . .env.secrets", "deny", "secret values"),
    ("root", "base64 env/api/.env", "deny", "secret values"),
    ("root", "diff env/api/.env env/api/secrets.txt", "deny", "secret values"),
    ("root", "cd env/api && cat .env", "deny", "secret values"),
    ("root", "echo hi && cat .env", "deny", "secret values"),
    ("root", "cat .env 2>&1", "deny", "secret values"),
    ("root", "sudo cat .env", "deny", "secret values"),
    ("root", "/bin/cat .env", "deny", "secret values"),
    ("root", "cat 'env/api/.env'", "deny", "secret values"),
    ("root", "gh pr merge 1 && cat .env", "deny", "secret values"),   # deny wins over ask
    # deny: dumping the environment
    ("root", "env", "deny", "printenv NAME"),
    ("root", "printenv", "deny", "dumps every environment variable"),
    ("root", "env | sort", "deny", "printenv NAME"),
    ("root", "FOO=1 env", "deny", "printenv NAME"),
    ("root", "export -p", "deny", "printenv NAME"),
    ("root", "declare -x", "deny", "printenv NAME"),
    ("root", "set", "deny", "printenv NAME"),
    ("root", "set | grep TOKEN", "deny", "printenv NAME"),
    # allowed look-alikes
    ("apif", "git push -u origin HEAD", "allow", ""),
    ("apif", "git push origin feat/x", "allow", ""),
    ("apif", "git push origin main", "allow", ""),                   # main is not the default branch of api
    ("web", "git push origin HEAD", "allow", ""),
    ("apif", "git push --tags", "allow", ""),
    ("apif", "git commit --amend", "allow", ""),
    ("apif", "git commit -m x", "allow", ""),
    ("root2", "git commit -m x", "allow", ""),
    ("root2", "git push", "allow", ""),
    ("root", "git rebase origin/main", "allow", ""),
    ("root", "git branch -a", "allow", ""),
    ("root", "git branch --show-current", "allow", ""),
    ("root", "git branch -vv", "allow", ""),
    ("root", "git branch --list 'd*'", "allow", ""),
    ("root", "gh pr create --fill", "allow", ""),
    ("root", "gh pr view 12", "allow", ""),
    ("root", "grep -rn export src/", "allow", ""),
    ("root", "cat .env.example", "allow", ""),
    ("root", "cat .env.sample .env.template .env.dist", "allow", ""),
    ("root", "cat env/README.md", "allow", ""),
    ("root", "cat src/.envrc", "allow", ""),
    ("root", "env FOO=1 make test", "allow", ""),
    ("root", "printenv HOME", "allow", ""),
    ("root", "export FOO=1", "allow", ""),
    ("root", "declare -x FOO=1", "allow", ""),
    ("root", "set -e", "allow", ""),
    ("root", "ls -la repos/api/.env", "allow", ""),
    ("root", "test -f env/api/.env", "allow", ""),
    ("root", "stat env/api/.env", "allow", ""),
    ("root", "chmod 600 env/api/.env", "allow", ""),
    ("root", "ln -s ../../env/api/.env repos/web/.env", "allow", ""),
    ("root", "cp env/api/.env /tmp/x", "allow", ""),
    ("root", "mv env/api/.env env/api/.env.old", "allow", ""),
    ("root", "rm env/api/.env", "allow", ""),
    ("root", "source env/api/.env", "allow", ""),
    ("root", ". env/api/.env", "allow", ""),
    ("root", "docker compose --env-file env/api/.env up", "allow", ""),
    ("root", 'echo "git push --force"', "allow", ""),
    ("root", "echo 'gh pr merge 1; cat .env'", "allow", ""),
    ("root", "git log --grep=--force", "allow", ""),
    ("root", "git log --oneline | head -5", "allow", ""),
    ("root", "git status 2>&1 | cat", "allow", ""),
    ("root", "git status && git diff", "allow", ""),
    ("root", "", "allow", ""),
    # branch changes earlier in the same command line
    ("api", "git checkout -b feat/x && git commit -m x", "allow", ""),
    ("api", "git switch -c feat/x && git commit -m x", "allow", ""),
    ("api", "git switch feat/other && git commit -m x", "allow", ""),
    ("api", "git checkout -b feat/x; git push -u origin HEAD", "allow", ""),
    ("root", "git -C repos/api checkout -b feat/x && git -C repos/api commit -m x", "allow", ""),
    ("root", "cd repos/api && git checkout -b feat/x && git commit -m x", "allow", ""),
    ("root", "git -C repos/api checkout -b feat/x && git commit -m x", "deny", "default branch (main)"),  # another directory
    ("apif", "git switch develop && git commit -m x", "deny", "default branch (develop)"),
    ("api", "git switch - && git commit -m x", "allow", ""),          # unknown target: nothing certain
    # directories
    ("root", "cd repos/api-feat && git commit -m x", "allow", ""),    # the cd leads off main
    ("root", "cd repos/missing && git commit -m x", "allow", ""),     # no such clone: not a repository
    ("root", "cd \"$SOMEWHERE\" && git commit -m x", "allow", ""),
    ("plain", "git commit -m x", "allow", ""),
    ("plain", "git push --force", "ask", "force-push"),               # asks do not need a repository
    ("det", "git commit -m x", "allow", ""),
    ("det", "git push", "allow", ""),
    # malformed command lines must not crash
    ("apif", 'git push --force "unterminated', "ask", "force-push"),
    ("root", 'echo "unterminated; git push --force', "allow", ""),
    ("root", "cat 'env/api/.env", "deny", "secret values"),
    ("root", "git -C", "allow", ""),
    ("root", "git", "allow", ""),
    ("root", "&& ; | |", "allow", ""),
    # several commands: the most severe wins
    ("apif", "echo hi && git push --force origin feat/x", "ask", "force-push"),
    ("apif", "git branch -D old; gh pr merge 1", "ask", ""),
    ("apif", "gh pr merge 1 | cat", "ask", "merging a PR"),
    ("apif", "gh pr merge 1 &\ncat .env", "deny", "secret values"),
    # finding 1: a plain checkout or switch moves the branch later commands run on
    ("root", "git checkout feat/zz && git commit -m x", "allow", ""),
    ("root", "git checkout feat/zz && git push -u origin HEAD", "allow", ""),
    ("root", "git switch feat/zz && git commit -m x", "allow", ""),
    ("root", "git checkout -q feat/zz && git commit -m x", "allow", ""),
    ("api", "git checkout -t origin/main && git commit -m x", "allow", ""),
    ("api", "git checkout --track origin/feat/q && git commit -m x", "allow", ""),
    ("root", "git switch --track origin/feat/q && git commit -m x", "allow", ""),
    ("web", "git checkout main && git commit -m x", "deny", "default branch (main)"),
    ("web", "git checkout main && git push -u origin HEAD", "deny", "default branch (main)"),
    ("apif", "git checkout -t origin/develop && git commit -m x", "deny", "default branch (develop)"),
    ("apif", "git switch --track origin/develop && git commit -m x", "deny", "default branch (develop)"),
    ("root", "git checkout README.md && git commit -m x", "deny", "default branch (main)"),       # a path, not a branch
    ("root", "git checkout -- README.md && git commit -m x", "deny", "default branch (main)"),
    ("root", "git checkout . && git commit -m x", "deny", "default branch (main)"),
    ("root", "git checkout HEAD~1 && git commit -m x", "deny", "default branch (main)"),
    ("root", "git checkout feat/zz -- README.md && git commit -m x", "deny", "default branch (main)"),
    ("web", "git checkout main README.md && git commit -m x", "allow", ""),                        # restores a file only
    ("root", "git checkout - && git commit -m x", "allow", ""),                                   # the previous branch: unknown
    ("root", "git switch --detach && git commit -m x", "allow", ""),
    ("root", "git checkout --detach && git commit -m x", "allow", ""),
    # finding 2: heredoc bodies are data
    ("root", "cat > deploy.sh <<'EOF'\ngit push origin main\nEOF", "allow", ""),
    ("root", "cat > x.sh <<EOF\ngit push --force\nEOF", "allow", ""),
    ("root", 'cat > x.sh << "EOF"\nenv\nset\ncat repos/app/.env\nEOF', "allow", ""),
    ("root", "cat <<-EOF\n\tgit push -f\n\tEOF", "allow", ""),
    ("apif", "cat <<'EOF' > x.sh\ngit push origin main\nEOF\ngit push --force", "ask", "force-push"),   # what follows still counts
    ("apif", "git push --force <<EOF\nbody\nEOF", "ask", "force-push"),                                # the owner is evaluated
    ("root", "cat <<EOF\nnever closed\ngit push origin main", "allow", ""),
    ("root", "cat <<<'x' && git commit -m x", "deny", "default branch (main)"),                        # a here-string is not a heredoc
    ("root", "cat <<A <<B\none\nA\ntwo\nB\ngit commit -m x", "deny", "default branch (main)"),
    # finding 3: only --tags alone is a tags-only push
    ("root", "git push --follow-tags", "deny", "default branch (main)"),
    ("root", "git push origin --follow-tags", "deny", "default branch (main)"),
    ("root", "git push --tags", "allow", ""),
    ("root", "git push origin --tags", "allow", ""),
    ("root", "git push --follow-tags origin feat/x", "allow", ""),
    # finding 4: groups and literal shell strings
    ("apif", "(git push -f)", "ask", "force-push"),
    ("apif", "( git push -f )", "ask", "force-push"),
    ("apif", "{ git push -f; }", "ask", "force-push"),
    ("apif", "echo hi && (git push -f; echo done)", "ask", "force-push"),
    ("apif", "bash -c 'git push -f'", "ask", "force-push"),
    ("apif", 'sh -c "git push --force origin feat/x"', "ask", "force-push"),
    ("root", "zsh -c 'git commit -m x'", "deny", "default branch (main)"),
    ("root", "bash -lc 'cat .env'", "deny", "secret values"),
    ("root", "bash -c \"bash -c 'git commit -m x'\"", "deny", "default branch (main)"),
    ("root", "bash -c 'cd repos/api-feat && git commit -m x'", "allow", ""),
    ("apif", 'bash -c "$CMD"', "allow", ""),
    ("apif", "bash -c 'git push -f $REMOTE'", "allow", ""),
    ("apif", "bash -c 'echo `date`; git push -f'", "allow", ""),
    ("apif", "bash script.sh -c git", "allow", ""),
    ("root", "(cd repos/api-feat && git status); git commit -m x", "deny", "default branch (main)"),   # the subshell cd does not leak
    ("root", "bash -c 'git checkout -b feat/q'; git commit -m x", "allow", ""),    # a checkout changes the repository, not the shell
    # review round: arithmetic shifts and comments are not heredocs
    ("apif", "echo $((1<<2))\ngit push -f", "ask", "force-push"),
    ("apif", "x=$((y<<1))\ngit push --force", "ask", "force-push"),
    ("apif", "echo hi # <<EOF\ngit push -f", "ask", "force-push"),
    ("apif", "(( x<<1 ))\ngit push -f", "ask", "force-push"),
    ("apif", "echo $(( (1<<2) + (3<<1) ))\ngit push -f", "ask", "force-push"),
    ("apif", 'echo "<<EOF"\ngit push -f', "ask", "force-push"),
    ("apif", "echo a#b <<EOF\ngit push -f\nEOF", "allow", ""),            # `#` inside a word is no comment
    ("apif", "cat <<EOF # note\ngit push -f\nEOF\ngit push -f", "ask", "force-push"),
    # review round: heredoc bodies that a shell runs
    ("apif", "sh <<EOF\ngit push -f\nEOF", "ask", "force-push"),
    ("apif", "cat <<EOF | sh\ngit push -f\nEOF", "ask", "force-push"),
    ("apif", "bash -s <<'EOF'\ngit push -f $X\nEOF", "ask", "force-push"),
    ("apif", "cat <<EOF | sudo bash -x\ngit push -f\nEOF", "ask", "force-push"),
    ("apif", "sh <<EOF && echo done\ngit push -f\nEOF", "ask", "force-push"),
    ("root", "sh <<EOF\ncat .env\nEOF", "deny", "secret values"),
    ("root", "bash <<EOF\ngit commit -m x\nEOF", "deny", "default branch (main)"),
    ("apif", "cat <<EOF | cat\ngit push -f\nEOF", "allow", ""),             # another owner: the body is data
    ("apif", "cat <<EOF | sh -c 'echo hi'\ngit push -f\nEOF", "allow", ""),  # -c: stdin is not the script
    ("apif", "sh script.sh <<EOF\ngit push -f\nEOF", "allow", ""),
    ("apif", "sh <<EOF\ngit push -f $X\nEOF", "allow", ""),                  # unquoted body: expanded first
    ("apif", "cat > x.sh <<EOF\ngit push -f\nEOF\nsh x.sh", "allow", ""),
    # review round: a checkout outlives a subshell, a cd does not
    ("web", "(git checkout main); git commit -m x", "deny", "default branch (main)"),
    ("web", "bash -c 'git checkout main' && git commit -m x", "deny", "default branch (main)"),
    ("web", "(git checkout main) && git commit -m x", "deny", "default branch (main)"),
    ("root", "(git checkout feat/a); git commit -m x", "allow", ""),
    ("root", "bash -c 'git switch feat/a'; git commit -m x", "allow", ""),
    ("root", "(cd repos/api-feat && git checkout -b feat/q); git commit -m x", "deny", "default branch (main)"),
    ("root", "(cd repos/api && git checkout -b feat/q; git commit -m x); git commit -m y", "deny", "default branch (main)"),
    # review round: redirections are not arguments
    ("web", "git checkout main 2>/dev/null && git commit -m x", "deny", "default branch (main)"),
    ("web", "git checkout main >/dev/null && git commit -m x", "deny", "default branch (main)"),
    ("web", "git checkout main &>/dev/null && git commit -m x", "deny", "default branch (main)"),
    ("web", "git checkout main 2>&1 && git commit -m x", "deny", "default branch (main)"),
    ("web", "git checkout main >> log && git commit -m x", "deny", "default branch (main)"),
    ("web", "git checkout main < file && git commit -m x", "deny", "default branch (main)"),
    ("web", "git checkout main 2> err && git commit -m x", "deny", "default branch (main)"),
    ("web", "git checkout 2>/dev/null main && git commit -m x", "deny", "default branch (main)"),
    ("web", "(git checkout main 2>/dev/null); git commit -m x", "deny", "default branch (main)"),
    ("root", "git checkout feat/a 2>/dev/null && git commit -m x", "allow", ""),
    ("root", "git checkout feat/a >/dev/null && git commit -m x", "allow", ""),
    ("root", "git checkout feat/a &>/dev/null && git commit -m x", "allow", ""),
    ("root", "git checkout feat/a 2>&1 && git commit -m x", "allow", ""),
    ("root", "git checkout feat/a >> log && git commit -m x", "allow", ""),
    ("root", "git checkout feat/a < file && git commit -m x", "allow", ""),
    ("root", "git switch feat/a 2>/dev/null && git commit -m x", "allow", ""),
    ("api", "git push origin 2>&1", "deny", "default branch (develop)"),
    ("api", "git push origin >/dev/null", "deny", "default branch (develop)"),
    ("apif", "git push -f 2>&1", "ask", "force-push"),
    ("root", "cat 2>err .env", "deny", "secret values"),
    ("root", "cat >out < .env", "deny", "secret values"),
    ("root", "cat <<<'x' .env", "deny", "secret values"),
    ("root", "echo hi > .env", "allow", ""),
    # review round: checkout forms
    ("web", "git checkout -p main && git commit -m x", "allow", ""),
    ("web", "git checkout --patch main && git commit -m x", "allow", ""),
    ("web", "git checkout --pathspec-from-file=f main && git commit -m x", "allow", ""),
    ("web", "git checkout --pathspec-from-file f main && git commit -m x", "allow", ""),
    ("apif", "git checkout -p develop && git commit -m x", "allow", ""),
    ("apif", "git checkout -pq develop && git commit -m x", "allow", ""),
    ("apif", "git checkout --pathspec-from-file=f develop && git commit -m x", "allow", ""),
    ("apif", "git checkout develop -- && git commit -m x", "deny", "default branch (develop)"),
    ("web", "git checkout main -- && git commit -m x", "deny", "default branch (main)"),
    ("web", "git checkout main -- README.md && git commit -m x", "allow", ""),
    ("web", "git checkout main && git commit -m x", "deny", "default branch (main)"),             # a directory `main` exists, so does the branch
    ("web", "git checkout README.md && git commit -m x", "allow", ""),
    ("root", "git checkout -bfeat/new && git commit -m x", "allow", ""),
    ("root", "git checkout -Bfeat/new && git commit -m x", "allow", ""),
    ("root", "git switch -cfeat/new && git commit -m x", "allow", ""),
    ("root", "git switch --create=feat/new && git commit -m x", "allow", ""),
    ("root", "git switch --create feat/new && git commit -m x", "allow", ""),
    ("root", "git switch --force-create=feat/new && git commit -m x", "allow", ""),
    ("root", "git checkout -qb feat/new && git commit -m x", "allow", ""),
    ("web", "git switch -cmain && git commit -m x", "deny", "default branch (main)"),
    ("web", "git checkout --conflict diff3 main && git commit -m x", "deny", "default branch (main)"),
    # review round: the interpreter's flags before -c
    ("apif", "bash -o pipefail -c 'git push -f'", "ask", "force-push"),
    ("apif", "bash +o pipefail -c 'git push -f'", "ask", "force-push"),
    ("apif", "bash -O extglob -c 'git push -f'", "ask", "force-push"),
    ("apif", "bash -ec 'git push -f'", "ask", "force-push"),
    ("apif", "bash -eo pipefail -c 'git push -f'", "ask", "force-push"),
    ("apif", "bash --norc -c 'git push -f'", "ask", "force-push"),
    ("apif", "bash --rcfile x -c 'git push -f'", "ask", "force-push"),
    ("apif", "bash -o pipefail script.sh -c 'git push -f'", "allow", ""),
    ("apif", "bash -o pipefail", "allow", ""),
    # finding 5: secret names on case-insensitive file systems
    ("root", "cat .ENV", "deny", "secret values"),
    ("root", "cat .Env.local", "deny", "secret values"),
    ("root", "cat ENV/api/secrets.txt", "deny", "secret values"),
    ("root", "cat Env/api/.gitkeep", "allow", ""),
    ("root", "cat Env/README.md", "allow", ""),
    ("root", "cat .ENV.EXAMPLE", "allow", ""),
    # finding 6: gh global flags before the subcommand
    ("apif", "gh -R o/r pr merge 12", "ask", "merging a PR"),
    ("apif", "gh --repo o/r pr merge 12", "ask", "merging a PR"),
    ("apif", "gh --hostname h.example pr merge 12", "ask", "merging a PR"),
    ("apif", "gh --repo=o/r pr merge 12", "ask", "merging a PR"),
    ("apif", "gh pr merge --help", "allow", ""),
    ("apif", "gh pr merge -h", "allow", ""),
    ("apif", "gh -R o/r pr view 12", "allow", ""),
    ("apif", "gh -R o/r issue merge", "allow", ""),
    # finding 7: the first commit of a new repository
    ("fresh", "git commit -m first", "allow", ""),
    ("fresh", "git add -A && git commit -m first", "allow", ""),
    ("freshorigin", "git commit -m first", "deny", "default branch (main)"),
    # finding 11: a bare export lists every exported variable
    ("root", "export", "deny", "printenv NAME"),
    ("root", "export FOO=bar", "allow", ""),
    ("root", "export FOO", "allow", ""),
]


# (tool, input, decision, fragment) with paths relative to the workspace root, cwd `root` unless "cwd" is given
FILE_CASES = [
    ("Read", {"file_path": "{root}/env/api/.env"}, "deny", "secret values"),
    ("Read", {"file_path": "{root}/.ENV"}, "deny", "secret values"),
    ("Write", {"file_path": "{web}/.Env.Local", "content": "x"}, "deny", "secret values"),
    ("Write", {"file_path": "{root}/ENV/new/x.json", "content": "x"}, "deny", "secret values"),
    ("Read", {"file_path": "{root}/env/api/secrets.txt"}, "deny", "secret values"),
    ("Read", {"file_path": "{root}/env/new/anything.json"}, "deny", "secret values"),    # does not exist yet
    ("Read", {"file_path": "{web}/.env.local"}, "deny", "read the `.example` template"),
    ("Edit", {"file_path": "{web}/.env", "old_string": "a", "new_string": "b"}, "deny", "secret values"),
    ("Write", {"file_path": "{root}/env/api/.env.production", "content": "x"}, "deny", "secret values"),
    ("MultiEdit", {"file_path": "{root}/env/api/.env", "edits": []}, "deny", "secret values"),
    ("NotebookEdit", {"notebook_path": "{root}/env/api/.env"}, "deny", "secret values"),
    ("Read", {"file_path": "{api}/.env"}, "deny", "secret values"),                      # symlink into env/
    ("Read", {"file_path": "{api}/link"}, "deny", "secret values"),                      # basename is harmless; the target is not
    ("Read", {"file_path": ".env", "cwd": "web"}, "deny", "secret values"),              # relative to cwd
    ("Read", {"file_path": "../../env/api/.env", "cwd": "api"}, "deny", "secret values"),
    ("Read", {"file_path": "link", "cwd": "api"}, "deny", "secret values"),
    ("Read", {"filePath": "{root}/env/api/.env"}, "deny", "secret values"),              # OpenCode spelling
    ("apply_patch", {"command": "*** Begin Patch\n*** Update File: env/api/.env\n@@\n-a\n+b\n*** End Patch\n"}, "deny", "secret values"),
    ("apply_patch", {"command": "*** Begin Patch\n*** Add File: src/x.py\n+x\n*** End Patch\n"}, "allow", ""),
    ("apply_patch", {"command": "*** Begin Patch\n*** Update File: a.py\n*** Move to: .env.local\n*** End Patch\n"}, "deny", "secret values"),
    ("Read", {"file_path": "{root}/.env.example"}, "allow", ""),
    ("Read", {"file_path": "{root}/.env.sample"}, "allow", ""),
    ("Read", {"file_path": "{root}/env/README.md"}, "allow", ""),
    ("Write", {"file_path": "{root}/env/api/.gitkeep", "content": ""}, "allow", ""),
    ("Read", {"file_path": "{root}/README.md"}, "allow", ""),
    ("Edit", {"file_path": "{root}/scripts/check.py"}, "allow", ""),
    ("Read", {"file_path": "{root}/repos/api/.envrc"}, "allow", ""),
    ("Read", {}, "allow", ""),
    ("Grep", {"pattern": "x", "path": "{root}/env"}, "allow", ""),                       # not a file tool of this guard
    ("Unknown", {"file_path": "{root}/env/api/.env"}, "allow", ""),
]


class DecideTests(Fixture):
    def test_shell_table(self):
        for where, command, expected, fragment in SHELL_CASES:
            with self.subTest(cwd=where, command=command):
                decision, reason = self.decide("Bash", {"command": command}, where)
                self.assertEqual(expected, decision, reason)
                self.assertIn(fragment, reason)
                if expected == "allow":
                    self.assertEqual("", reason)

    def test_shell_tool_names(self):
        for tool in ("bash", "Bash", "shell", "exec_command"):
            with self.subTest(tool=tool):
                self.assertEqual("ask", self.decide(tool, {"command": "git push -f"}, "apif")[0])

    def test_file_table(self):
        for tool, tool_input, expected, fragment in FILE_CASES:
            with self.subTest(tool=tool, input=tool_input):
                tool_input = dict(tool_input)
                where = tool_input.pop("cwd", "root")
                tool_input = {k: v.format(**self.paths) if isinstance(v, str) else v for k, v in tool_input.items()}
                decision, reason = self.decide(tool, tool_input, where)
                self.assertEqual(expected, decision, reason)
                self.assertIn(fragment, reason)

    def test_manifest_paths_are_normalized_like_check_py(self):
        tmp = Path(tempfile.mkdtemp(prefix="guard-norm-"))
        self.addCleanup(shutil.rmtree, str(tmp), True)
        (tmp / "clones" / "api").mkdir(parents=True)
        (tmp / "repos.json").write_text(json.dumps({"org": "a", "root": "x/../clones", "repos": [
            {"name": "api", "url": "u", "path": "./api/", "branch": "develop"},
            {"name": "bad", "url": "u", "path": "../outside", "branch": "nope"}]}))
        top, root = os.path.realpath(str(tmp / "clones" / "api")), os.path.realpath(str(tmp))
        self.assertEqual("develop", guard.manifest_default_branch(top, root))
        self.assertIsNone(guard.manifest_default_branch(os.path.realpath(str(tmp / "outside")), root))

    def test_root_is_where_env_lives(self):
        other = Path(self.tmp) / "plain"
        self.assertEqual("allow", guard.decide("Read", {"file_path": str(other / "env" / "x")}, str(other), self.paths["root"])[0])
        self.assertEqual("deny", guard.decide("Read", {"file_path": str(other / "env" / "x")}, str(other), str(other))[0])

    def test_never_raises(self):
        for tool_input in (None, "x", [], {"command": None}, {"command": 7}, {"command": ["git", "push", "-f"]}):
            with self.subTest(tool_input=tool_input):
                self.assertIn(self.decide("Bash", tool_input, "apif")[0], ("allow", "ask"))
        self.assertEqual("allow", guard.decide(None, {}, None, None)[0])

    def test_internal_error_allows_with_a_note(self):
        err = io.StringIO()
        with mock.patch.object(guard, "decide_shell", side_effect=RuntimeError("boom")), redirect_stderr(err):
            self.assertEqual(("allow", ""), self.decide("Bash", {"command": "git push -f"}, "apif"))
        self.assertEqual(1, len(err.getvalue().splitlines()))
        self.assertIn("boom", err.getvalue())

    def test_shared_secret_name_definition(self):
        spec = importlib.util.spec_from_file_location("check_for_guard", str(REPO / "scripts" / "check.py"))
        check = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(check)
        for base in (".env", ".env.local", ".env.example", ".env.dist", "env", ".envrc", "x.env", ".ENV", ".Env.Local", ".ENV.EXAMPLE"):
            self.assertEqual(check.is_env_secret_name(base), guard.is_env_secret_name(base), base)


def make_sibling_layout(base, first, second):
    """Siblings `r` and `r2` under `base`, on the given branches; `main` is the default branch of both."""
    for name, branch in (("r", first), ("r2", second)):
        repo = base / name
        make_repo(repo, "main")
        run(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        run(repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
        if branch != "main":
            run(repo, "checkout", "-q", "-b", branch)


# (command, decision, reason fragment), each run from `r` on main with `r2` on feat/a
SCOPE_CASES = [
    # a word that ends in `)` is not the end of a subshell
    ('(cd ../r2 && git commit -m "fix (x)" && git push)', "allow", ""),
    ("(cd ../r2; x=$(git rev-parse HEAD); git commit -m x)", "allow", ""),
    ('(cd ../r2; echo ")"; git commit -m x)', "allow", ""),
    ("(cd ../r2; echo $(echo a); git commit -m x)", "allow", ""),
    ("(cd ../r2; echo `echo a`; git commit -m x)", "allow", ""),
    ('echo "a (b"; (cd ../r2 && git commit -m x)', "allow", ""),
    # the real end of the subshell still restores the directory
    ("(cd ../r2; git commit -m x); git commit -m y", "deny", "default branch (main)"),
    ("(cd ../r2 && git status); git commit -m x", "deny", "default branch (main)"),
    ("(cd ../r2 && git status) && git commit -m x", "deny", "default branch (main)"),
    ('git commit -m "fix (x)"', "deny", "default branch (main)"),
    ("( (cd ../r2; git commit -m x) ); git commit -m y", "deny", "default branch (main)"),
    # `do`, `then`, `else` and `{` introduce a command
    ("for d in a; do (cd ../r2 && git commit -m x); done", "allow", ""),
    ("for d in a; do git commit -m x; done", "deny", "default branch (main)"),
    ("if true; then (cd ../r2; git commit -m x); fi", "allow", ""),
    ("if true; then git commit -m x; fi", "deny", "default branch (main)"),
    ("if false; then echo a; else git commit -m x; fi", "deny", "default branch (main)"),
    ("{ git commit -m x; }", "deny", "default branch (main)"),
    ("while true; do git commit -m x; done", "deny", "default branch (main)"),
    # `bash -s` reads commands from stdin; the other words are positional parameters
    ("cd ../r2 && bash -s -- arg <<'EOF'\ngit push -f\nEOF", "ask", "force-push"),
    ("cd ../r2 && bash -s arg <<'EOF'\ngit push -f\nEOF", "ask", "force-push"),
    ("cd ../r2 && bash -s -x arg <<'EOF'\ngit push -f\nEOF", "ask", "force-push"),
    ("cd ../r2 && bash script.sh <<'EOF'\ngit push -f\nEOF", "allow", ""),
    # `bash -c` skips `--`
    ("cd ../r2 && bash -c -- 'git push -f'", "ask", "force-push"),
    ("cd ../r2 && bash -c -x 'git push -f'", "ask", "force-push"),
    # `env` wraps a command
    ("cd ../r2 && env git push -f", "ask", "force-push"),
    ("cd ../r2 && env FOO=1 git push -f", "ask", "force-push"),
    ("cd ../r2 && env -i git push -f", "ask", "force-push"),
    ("cd ../r2 && env -u X FOO=1 git push -f", "ask", "force-push"),
    ("cd ../r2 && env -- git push -f", "ask", "force-push"),
    ("cd ../r2 && env bash -c 'git push -f'", "ask", "force-push"),
    ("env git commit -m x", "deny", "default branch (main)"),
    ("env FOO=1 make test", "allow", ""),
    ("env", "deny", "environment"),
    ("env | cat", "deny", "environment"),
    ("env FOO=1", "deny", "environment"),
    ("env -i", "deny", "environment"),
    ("env -C ../r2 git commit -m x", "allow", ""),   # r2 is on a feature branch
    ("env -C ../r git commit -m x", "deny", "default branch (main)"),   # the directory given is the effective one
    ("env --chdir ../r git commit -m x", "deny", "default branch (main)"),
    ("env --chdir=../r2 git commit -m x", "allow", ""),
    ("cd ../r2 && env -C . git push -f", "ask", "force-push"),
    ("cd ../r2 && env --chdir=. git push --force", "ask", "force-push"),
    ("env -C . git push -f", "deny", "default branch (main)"),   # r is on main: the push to main is denied first
    ("env -C ../r2 git push -f", "ask", "force-push"),
    ("env -S 'git push -f'", "allow", ""),   # a string to split: we cannot know
    # combined short flags; `-u` takes a value
    ("env -iu FOO git commit -m x", "deny", "default branch (main)"),
    ("env -iuFOO git commit -m x", "deny", "default branch (main)"),
    ("env -iC ../r git commit -m x", "deny", "default branch (main)"),
    ("env -i -u FOO -u BAR git commit -m x", "deny", "default branch (main)"),
    # a wrapper followed by a subshell
    ("time (cd ../r2; git commit -m x)", "allow", ""),
    ("time (cd ../r2; git commit -m x); git commit -m y", "deny", "default branch (main)"),
    ("nohup (cd ../r2 && git commit -m x)", "allow", ""),
]


class ScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix="guard-scope-"))
        make_sibling_layout(cls.tmp / "a", "main", "feat/a")
        make_sibling_layout(cls.tmp / "b", "feat/a", "main")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(str(cls.tmp), True)

    def test_scope_table(self):
        cwd = str(self.tmp / "a" / "r")
        for command, expected, fragment in SCOPE_CASES:
            with self.subTest(command=command):
                decision, reason = guard.decide("Bash", {"command": command}, cwd, cwd)
                self.assertEqual(expected, decision, reason)
                self.assertIn(fragment, reason)

    def test_command_substitution_does_not_close_the_scope(self):
        cwd = str(self.tmp / "b" / "r")   # r on feat/a, r2 on main
        decision, reason = guard.decide("Bash", {"command": "(cd ../r2; v=$(cat README); git commit -m x)"}, cwd, cwd)
        self.assertEqual("deny", decision, reason)
        self.assertIn("default branch (main)", reason)

    def test_scanner_marks_only_grouping_parentheses(self):
        text = guard.mark_groups('(a "(b)" $(c) `d)` e) && (f); g=$(h; i)')
        self.assertEqual(2, text.count(guard.GROUP_OPEN))
        self.assertEqual(2, text.count(guard.GROUP_CLOSE))


class AdapterTests(Fixture):
    def call(self, agent, payload, raw=None):
        res = subprocess.run([sys.executable, str(GUARD), "--agent", agent], input=raw if raw is not None else json.dumps(payload),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        return res.returncode, res.stdout, res.stderr

    def claude(self, tool, tool_input, where="apif"):
        return self.call("claude", {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input,
                                    "cwd": self.paths[where]})

    def codex(self, tool, tool_input, where="apif"):
        return self.call("codex", {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input,
                                   "cwd": self.paths[where], "turn_id": "t1", "tool_use_id": "u1"})

    def opencode(self, tool, args, where="apif"):
        return self.call("opencode", {"tool": tool, "args": args, "cwd": self.paths[where]})

    SECRET = {"file_path": str(REPO / "env" / "api" / ".env")}

    def test_claude_allow(self):
        self.assertEqual((0, "", ""), self.claude("Bash", {"command": "git push -u origin HEAD"}))

    def test_claude_ask(self):
        code, out, _ = self.claude("Bash", {"command": "git push --force origin feat/x"})
        self.assertEqual(0, code)
        answer = json.loads(out)["hookSpecificOutput"]
        self.assertEqual("PreToolUse", answer["hookEventName"])
        self.assertEqual("ask", answer["permissionDecision"])
        self.assertIn("force-push", answer["permissionDecisionReason"])

    def test_claude_deny(self):
        code, out, _ = self.claude("Read", self.SECRET)
        self.assertEqual(0, code)
        answer = json.loads(out)["hookSpecificOutput"]
        self.assertEqual("deny", answer["permissionDecision"])
        self.assertIn("secret values", answer["permissionDecisionReason"])

    def test_codex_allow(self):
        self.assertEqual((0, "", ""), self.codex("Bash", {"command": "gh pr view 3"}))

    def test_codex_ask_is_a_block_that_says_to_ask(self):
        code, out, _ = self.codex("Bash", {"command": "git push --force origin feat/x"})
        self.assertEqual(0, code)
        answer = json.loads(out)["hookSpecificOutput"]
        self.assertEqual("deny", answer["permissionDecision"])
        self.assertIn("force-push", answer["permissionDecisionReason"])
        self.assertIn("ask the user to run this command themselves or to confirm", answer["permissionDecisionReason"])

    def test_codex_deny(self):
        patch = "*** Begin Patch\n*** Update File: %s\n@@\n-a\n+b\n*** End Patch\n" % self.SECRET["file_path"]
        code, out, _ = self.codex("apply_patch", {"command": patch})
        self.assertEqual(0, code)
        answer = json.loads(out)["hookSpecificOutput"]
        self.assertEqual("deny", answer["permissionDecision"])
        self.assertNotIn("ask the user", answer["permissionDecisionReason"])
        self.assertIn("secret values", answer["permissionDecisionReason"])

    def test_opencode_allow(self):
        code, out, _ = self.opencode("bash", {"command": "git branch -a"})
        self.assertEqual((0, {"decision": "allow"}), (code, json.loads(out)))

    def test_opencode_ask_is_a_block_that_says_to_ask(self):
        code, out, _ = self.opencode("bash", {"command": "gh pr merge 4"})
        answer = json.loads(out)
        self.assertEqual((0, "deny"), (code, answer["decision"]))
        self.assertIn("merging a PR", answer["reason"])
        self.assertIn("ask the user to run this command themselves or to confirm", answer["reason"])

    def test_opencode_deny(self):
        code, out, _ = self.opencode("read", {"filePath": self.SECRET["file_path"]})
        answer = json.loads(out)
        self.assertEqual((0, "deny"), (code, answer["decision"]))
        self.assertIn("secret values", answer["reason"])

    def test_bad_input_allows_with_a_note(self):
        for agent, empty in (("claude", ""), ("codex", ""), ("opencode", json.dumps({"decision": "allow"}))):
            with self.subTest(agent=agent):
                code, out, err = self.call(agent, None, raw="not json")
                self.assertEqual(0, code)
                self.assertEqual(empty, out.strip())
                self.assertEqual(1, len(err.splitlines()))

    def test_explain(self):
        res = subprocess.run([sys.executable, str(GUARD), "--explain", "cd repos/api && git commit -m x"], cwd=str(REPO),
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
        self.assertEqual((0, "allow\n", ""), (res.returncode, res.stdout, res.stderr))
        res = subprocess.run([sys.executable, str(GUARD), "--explain", "cat env/api/.env"], cwd=str(REPO),
                             stdout=subprocess.PIPE, universal_newlines=True)
        self.assertEqual(0, res.returncode)
        self.assertTrue(res.stdout.startswith("deny: secret values"))

    def test_script_is_executable(self):
        self.assertTrue(os.access(str(GUARD), os.X_OK))


class ShippedConfigTests(unittest.TestCase):
    """The files that wire the script into each agent keep the shape their documentation asks for."""

    def test_claude_settings(self):
        data = json.loads((REPO / ".claude" / "settings.json").read_text())
        self.assertEqual(["hooks"], list(data))
        group = data["hooks"]["PreToolUse"][0]
        self.assertEqual("Bash|Read|Edit|Write|MultiEdit|NotebookEdit", group["matcher"])
        self.assertIn("$CLAUDE_PROJECT_DIR/scripts/guard.py", group["hooks"][0]["command"])
        self.assertIn("--agent claude", group["hooks"][0]["command"])

    def test_codex_hooks(self):
        group = json.loads((REPO / ".codex" / "hooks.json").read_text())["hooks"]["PreToolUse"][0]
        self.assertIn("Bash", group["matcher"])
        self.assertIn("--agent codex", group["hooks"][0]["command"])
        self.assertNotIn("show-toplevel", group["hooks"][0]["command"])

    def test_codex_hook_finds_the_workspace_root_from_inside_a_clone(self):
        command = json.loads((REPO / ".codex" / "hooks.json").read_text())["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        tmp = Path(tempfile.mkdtemp(prefix="guard-codex-"))
        self.addCleanup(shutil.rmtree, str(tmp), True)

        def stub(directory, name):
            (directory / "scripts").mkdir(parents=True)
            (directory / "scripts" / "guard.py").write_text("import sys\nprint(%r, *sys.argv[1:])\n" % name)

        outer, clone = tmp / "ws", tmp / "ws" / "repos" / "app"
        (outer / "repos.json").parent.mkdir(parents=True)
        (outer / "repos.json").write_text("{}")
        stub(outer, "outer")
        stub(clone, "decoy")     # the clone's own scripts/guard.py, with no repos.json beside it
        nested = clone / "src" / "deep"
        nested.mkdir(parents=True)

        def run_hook(cwd):
            return subprocess.run(["/bin/sh", "-c", command], cwd=str(cwd), stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, universal_newlines=True)

        for cwd in (nested, clone, outer):
            with self.subTest(cwd=str(cwd)):
                res = run_hook(cwd)
                self.assertEqual((0, "outer --agent codex\n"), (res.returncode, res.stdout), res.stderr)
        elsewhere = tmp / "elsewhere"
        elsewhere.mkdir()
        res = run_hook(elsewhere)
        self.assertEqual((0, ""), (res.returncode, res.stdout))

    def test_opencode_plugin(self):
        text = (REPO / ".opencode" / "plugins" / "guard.js").read_text()
        self.assertIn("execute.before", text)
        self.assertIn("scripts/guard.py", text)
        self.assertIn("--agent", text)
        self.assertNotIn("import { Plugin }", text)   # no package import: a fresh clone needs no install
        self.assertFalse((REPO / ".opencode" / "package.json").exists())


if __name__ == "__main__":
    unittest.main()
