"""Tests of the shell scripts (repo-check, link-skills, status, init --list) in a temp workspace.

Each test copies scripts/ and the Makefile into a throwaway workspace with fake clones (plain
`git init` directories) and runs the real scripts with bash. Requires git and jq, like the scripts.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASH = "/bin/bash" if os.path.exists("/bin/bash") else shutil.which("bash")

# name -> (manifest extras, files in the clone). `ghost` is cloned but not in the manifest.
CLONES = {
    "alpha": ({"check": "true"}, {"AGENTS.md": "# alpha rules\n"}),
    "beta": ({"check": "echo here:$(pwd)/ && exit 3", "path": "beta-dir"}, {}),
    "gamma": ({}, {}),
}
GHOST = ("ghost", {"AGENTS.md": "# ghost rules\n"})


def run(cmd, cwd, **kwargs):
    return subprocess.run(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True, **kwargs)


def clone(ws, rel, files):
    path = ws / "repos" / rel
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    for name, text in files.items():
        (path / name).write_text(text)
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(path), "-c", "user.name=t", "-c", "user.email=t@example.com",
                    "commit", "-q", "--allow-empty", "-m", "init"], check=True)


class Workspace(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="scripts-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ws = Path(self.tmp).resolve() / "ws"
        self.ws.mkdir()
        shutil.copytree(str(REPO / "scripts"), str(self.ws / "scripts"),
                        ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(str(REPO / "Makefile"), str(self.ws / "Makefile"))
        self.write_manifest(CLONES)
        for name, (extra, files) in CLONES.items():
            clone(self.ws, extra.get("path", name), files)
        clone(self.ws, GHOST[0], GHOST[1])

    def write_manifest(self, clones):
        repos = []
        for name, (extra, _) in clones.items():
            entry = {"name": name, "url": "git@example.com:acme/%s.git" % name}
            entry.update(extra)
            repos.append(entry)
        (self.ws / "repos.json").write_text(json.dumps({"org": "acme", "root": "repos", "repos": repos}))

    def sh(self, script, *args, **kwargs):
        return run([BASH, str(self.ws / "scripts" / script)] + list(args), self.ws, **kwargs)

    def skill_dir(self, name):
        return self.ws / ".agents" / "skills" / (name + "--instructions")

    def skill_text(self, name):
        return (self.skill_dir(name) / "SKILL.md").read_text()


class RepoCheckTests(Workspace):
    def test_exit_status_zero(self):
        r = self.sh("repo-check.sh", "alpha")
        self.assertEqual(0, r.returncode, r.stderr)

    def test_exit_status_passthrough(self):
        r = self.sh("repo-check.sh", "beta")
        self.assertEqual(3, r.returncode, r.stderr)

    def test_announces_the_command_on_stderr(self):
        r = self.sh("repo-check.sh", "alpha")
        self.assertIn("repo-check alpha: true (in %s)" % (self.ws / "repos" / "alpha"), r.stderr)

    def test_runs_inside_the_clone_resolved_from_path(self):
        r = self.sh("repo-check.sh", "beta")
        self.assertIn("here:%s/" % (self.ws / "repos" / "beta-dir"), r.stdout)

    def test_extra_arguments_are_a_usage_error(self):
        for args in (("alpha", "x"), ("alpha", "--", "x")):
            r = self.sh("repo-check.sh", *args)
            self.assertEqual(2, r.returncode, r.stderr)
            self.assertIn("exactly one argument", r.stderr)
            self.assertIn("inside the clone", r.stderr)

    def test_check_ending_in_a_comment_runs_as_written(self):
        self.write_manifest({"alpha": ({"check": "printf '[%s]' ok # comment"}, {})})
        r = self.sh("repo-check.sh", "alpha")
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertEqual("[ok]", r.stdout)

    def test_check_ending_in_a_semicolon_runs_as_written(self):
        self.write_manifest({"alpha": ({"check": "echo semi;"}, {})})
        r = self.sh("repo-check.sh", "alpha")
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertEqual("semi\n", r.stdout)

    def test_make_target_passes_the_repo(self):
        r = run(["make", "repo-check", "REPO=beta"], self.ws)
        self.assertEqual(2, r.returncode)  # make reports the failing recipe
        self.assertIn("repo-check beta:", r.stderr)

    def test_no_name_prints_usage_and_declaring_repos(self):
        r = self.sh("repo-check.sh")
        self.assertEqual(2, r.returncode)
        self.assertIn("no repo name given", r.stderr)
        self.assertIn("usage:", r.stderr)
        self.assertIn("alpha", r.stderr)
        self.assertNotIn("gamma", r.stderr)

    def test_make_without_repo_prints_usage(self):
        r = run(["make", "repo-check"], self.ws)
        self.assertNotEqual(0, r.returncode)
        self.assertIn("no repo name given", r.stderr)

    def test_unknown_name(self):
        r = self.sh("repo-check.sh", "nope")
        self.assertEqual(2, r.returncode)
        self.assertIn("'nope' is not in repos.json", r.stderr)

    def test_not_cloned(self):
        shutil.rmtree(str(self.ws / "repos" / "alpha"))
        r = self.sh("repo-check.sh", "alpha")
        self.assertEqual(2, r.returncode)
        self.assertIn("is not cloned", r.stderr)
        self.assertIn("make sync ONLY=alpha", r.stderr)

    def test_no_check_declared(self):
        r = self.sh("repo-check.sh", "gamma")
        self.assertEqual(2, r.returncode)
        self.assertIn('declares no "check" command', r.stderr)
        self.assertIn("package.json", r.stderr)
        self.assertIn("repos.json", r.stderr)


class LinkSkillsTests(Workspace):
    def link(self):
        r = self.sh("link-skills.sh")
        self.assertEqual(0, r.returncode, r.stderr)
        return r

    def snapshot(self):
        out = {}
        for base in (".agents/skills", ".claude/skills"):
            for p in sorted((self.ws / base).glob("*--*")):
                out[str(p.relative_to(self.ws))] = os.readlink(str(p)) if p.is_symlink() else (p / "SKILL.md").read_text()
        return out

    def test_which_skills_exist(self):
        r = self.link()
        for name in ("alpha", "beta-dir", "ghost"):
            self.assertTrue(self.skill_dir(name).is_dir(), name)
        self.assertFalse(self.skill_dir("gamma").exists())
        self.assertIn("3 instruction skills generated", r.stdout)

    def test_generated_skills_are_exposed_to_claude(self):
        self.link()
        for name in ("alpha", "beta-dir", "ghost"):
            link = self.ws / ".claude" / "skills" / (name + "--instructions")
            self.assertTrue(link.is_symlink(), name)
            self.assertTrue((link / "SKILL.md").is_file(), name)
        self.assertFalse((self.ws / ".claude" / "skills" / "gamma--instructions").exists())

    def test_frontmatter_and_marker(self):
        self.link()
        text = self.skill_text("alpha")
        self.assertTrue(text.startswith("---\nname: alpha--instructions\ndescription: Mandatory rules of the alpha repository."))
        self.assertTrue((self.skill_dir("alpha") / ".generated-by-link-skills").exists())

    def test_check_line_present_only_when_declared(self):
        self.link()
        self.assertIn("make repo-check REPO=alpha", self.skill_text("alpha"))
        self.assertIn("runs `true` in", self.skill_text("alpha"))
        self.assertIn("make repo-check REPO=beta", self.skill_text("beta-dir"))
        self.assertNotIn("repo-check", self.skill_text("ghost"))

    def test_instructions_pointer_present_only_with_files(self):
        self.link()
        self.assertIn("read `repos/alpha/AGENTS.md`", self.skill_text("alpha"))
        self.assertIn("read `repos/ghost/AGENTS.md`", self.skill_text("ghost"))
        self.assertNotIn("read `", self.skill_text("beta-dir"))

    def test_rules_override_the_workspace_instructions_for_that_repository(self):
        self.link()
        text = " ".join(self.skill_text("alpha").split())
        self.assertIn("They override the workspace's `AGENTS.md` and `docs/agents/` for that repository.", text)
        self.assertNotIn("meta AGENTS.md", text)

    def test_no_instructions_sentence(self):
        self.link()
        text = self.skill_text("beta-dir")
        self.assertIn("has no `AGENTS.md`", text)
        self.assertIn("propose", text)
        self.assertNotIn("has no `AGENTS.md`", self.skill_text("alpha"))

    def test_manifest_name_and_path_lookup(self):
        # beta's clone directory is beta-dir (manifest path): the skill is named after the directory
        # and the make command after the manifest name.
        self.link()
        self.assertTrue(self.skill_dir("beta-dir").is_dir())
        self.assertIn("REPO=beta`", self.skill_text("beta-dir"))
        self.assertFalse(self.skill_dir("beta").exists())
        self.assertIn("make repo-check REPO=beta", self.skill_text("beta-dir"))

    def test_second_run_is_idempotent(self):
        self.link()
        first = self.snapshot()
        self.link()
        self.assertEqual(first, self.snapshot())

    def test_skill_disappears_when_the_repo_no_longer_qualifies(self):
        self.link()
        self.write_manifest({"alpha": ({}, {}), "beta": ({"check": "true", "path": "beta-dir"}, {}), "gamma": ({}, {})})
        (self.ws / "repos" / "alpha" / "AGENTS.md").unlink()
        shutil.rmtree(str(self.ws / "repos" / "ghost"))
        r = self.link()
        self.assertFalse(self.skill_dir("alpha").exists())
        self.assertFalse((self.ws / ".claude" / "skills" / "alpha--instructions").is_symlink())
        self.assertFalse(self.skill_dir("ghost").exists())
        self.assertTrue(self.skill_dir("beta-dir").is_dir())
        self.assertIn("1 instruction skills generated", r.stdout)

    def test_import_only_claude_md_is_not_instructions(self):
        (self.ws / "repos" / "gamma" / "CLAUDE.md").write_text("@AGENTS.md\n")
        self.link()
        self.assertFalse(self.skill_dir("gamma").exists())
        self.write_manifest({"gamma": ({"check": "true"}, {})})
        self.link()
        self.assertIn("has no `AGENTS.md`", self.skill_text("gamma"))

    def test_clone_only_in_the_main_checkout_says_to_sync_first(self):
        main = self.ws
        subprocess.run(["git", "init", "-q", str(main)], check=True)
        subprocess.run(["git", "-C", str(main), "-c", "user.name=t", "-c", "user.email=t@example.com",
                        "commit", "-q", "--allow-empty", "-m", "init"], check=True)
        wt = Path(self.tmp).resolve() / "wt"
        subprocess.run(["git", "-C", str(main), "worktree", "add", "-q", str(wt)], check=True)
        shutil.copytree(str(REPO / "scripts"), str(wt / "scripts"), ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(str(main / "repos.json"), str(wt / "repos.json"))
        clone(wt, "alpha", {"AGENTS.md": "# own\n"})  # alpha is cloned in the worktree too
        r = run([BASH, str(wt / "scripts" / "link-skills.sh")], wt)
        self.assertEqual(0, r.returncode, r.stderr)
        own = (wt / ".agents/skills/alpha--instructions/SKILL.md").read_text()
        self.assertIn("make repo-check REPO=alpha", own)
        self.assertNotIn("not cloned in this checkout", own)
        borrowed = (wt / ".agents/skills/beta-dir--instructions/SKILL.md").read_text()
        self.assertIn("not cloned in this checkout", borrowed)
        self.assertIn("make sync ONLY=beta", borrowed)
        self.assertIn("then `make repo-check REPO=beta`", borrowed)

    def test_repo_skills_are_still_linked(self):
        skill = self.ws / "repos" / "gamma" / ".agents" / "skills" / "demo"
        skill.mkdir(parents=True)
        (skill / "SKILL.md").write_text("---\nname: demo\ndescription: d\n---\n")
        r = self.link()
        self.assertTrue((self.ws / ".claude" / "skills" / "gamma--demo").is_symlink())
        self.assertIn("1 linked", r.stdout)


class StatusTests(Workspace):
    def rows(self, out):
        rows = {}
        for line in out.splitlines()[1:]:
            parts = line.split()
            if parts and parts[0] in ("alpha", "beta-dir", "gamma", "ghost"):
                rows[parts[0]] = parts
        return rows

    def test_columns_per_repo_and_summary(self):
        r = self.sh("status.sh")
        self.assertEqual(0, r.returncode, r.stderr)
        header = r.stdout.splitlines()[0].split()
        self.assertEqual(["REPO", "BRANCH", "DIRTY", "AGENTS", "CHECK", "AHEAD/BEHIND"], header)
        rows = self.rows(r.stdout)
        agents, check = header.index("AGENTS"), header.index("CHECK")
        self.assertEqual(("yes", "yes"), (rows["alpha"][agents], rows["alpha"][check]))
        self.assertEqual(("no", "yes"), (rows["beta-dir"][agents], rows["beta-dir"][check]))
        self.assertEqual(("no", "no"), (rows["gamma"][agents], rows["gamma"][check]))
        self.assertEqual(("yes", "no"), (rows["ghost"][agents], rows["ghost"][check]))
        self.assertTrue(r.stdout.rstrip().endswith("2 repo(s) without instructions, 2 without a check command"), r.stdout)

    def test_claude_md_counts_as_instructions(self):
        (self.ws / "repos" / "gamma" / "CLAUDE.md").write_text("rules\n")
        r = self.sh("status.sh")
        self.assertEqual("yes", self.rows(r.stdout)["gamma"][3])

    def test_import_only_claude_md_is_not_instructions(self):
        (self.ws / "repos" / "gamma" / "CLAUDE.md").write_text("@AGENTS.md\n")
        r = self.sh("status.sh")
        self.assertEqual("no", self.rows(r.stdout)["gamma"][3])
        self.assertTrue(r.stdout.rstrip().endswith("2 repo(s) without instructions, 2 without a check command"), r.stdout)

    def test_no_summary_when_every_clone_has_both(self):
        shutil.rmtree(str(self.ws / "repos" / "beta-dir"))
        shutil.rmtree(str(self.ws / "repos" / "gamma"))
        shutil.rmtree(str(self.ws / "repos" / "ghost"))
        self.write_manifest({"alpha": ({"check": "true"}, {})})
        r = self.sh("status.sh")
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertNotIn("without", r.stdout)
        self.assertEqual(2, len(r.stdout.splitlines()))


class ListTests(Workspace):
    def test_check_is_the_last_column_and_dash_when_absent(self):
        r = self.sh("init.sh", "--list")
        self.assertEqual(0, r.returncode, r.stderr)
        lines = {l.split()[0]: l for l in r.stdout.splitlines()}
        self.assertTrue(lines["alpha"].endswith("acme/alpha.git  true"), lines["alpha"])
        self.assertTrue(lines["beta"].endswith("echo here:$(pwd)/ && exit 3"), lines["beta"])
        self.assertTrue(lines["gamma"].rstrip().endswith(" -"), lines["gamma"])

    def test_branch_column_is_main_when_omitted(self):
        self.write_manifest({"nobranch": ({}, {}), "dev": ({"branch": "develop"}, {})})
        r = self.sh("init.sh", "--list")
        self.assertEqual(0, r.returncode, r.stderr)
        rows = {l.split()[0]: l.split() for l in r.stdout.splitlines()}
        self.assertEqual("main", rows["nobranch"][1], r.stdout)
        self.assertEqual("develop", rows["dev"][1], r.stdout)
        self.assertNotIn("null", r.stdout)

    def test_empty_manifest(self):
        self.write_manifest({})
        r = self.sh("init.sh", "--list")
        self.assertEqual(0, r.returncode, r.stderr)
        self.assertEqual("", r.stdout)


if __name__ == "__main__":
    unittest.main()
