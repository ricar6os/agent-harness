"""Contract tests for the OpenSpec CLI: the commands OpenSpec's workflow skills call, run against this
repository's schema and config.

They fail when a CLI upgrade stops handing the schema's rules and the config's hooks to those
skills, or when a template of the schema no longer passes strict validation. Skipped when the CLI is not installed at a
version that openspec/cli-version accepts; CI installs that version, so they always run there.
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("check", str(REPO / "scripts" / "check.py"))
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)

SCHEMA = REPO / "openspec" / "schemas" / "spec-plan"
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)


def fill(template, values):
    """The template with each `<!-- ... -->` placeholder replaced, in order, by the next value."""
    pending = list(values)
    text = COMMENT_RE.sub(lambda _match: pending.pop(0), template)
    assert not pending, "unused values: %r" % pending
    return text


def spec_from_template():
    return fill((SCHEMA / "templates" / "spec.md").read_text(), [
        "Greets a shopper by name when they open the shop, so the page feels personal.",
        "",
        "Greet by name",
        "return a greeting that contains the given name",
        "Known name",
        'the name "Ana"',
        "a greeting is requested",
        'the response is "Hello, Ana"',
    ])


PLAN = """\
---
name: "add-greeting"
---

# Add greeting

## Phases

### Phase 1: Greeting endpoint [ABC-1]

**Repos:** api → web

- [x] api: add the endpoint
- [ ] Run the verification command of every repo this phase touched.

### Phase 2: Greeting screen

- [ ] web: add the screen
"""


class OpenSpecContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pin, _ = check.pinned_openspec_version(REPO)
        installed = check.installed_openspec_version()
        if not check.version_satisfies(installed, pin):
            raise unittest.SkipTest("openspec %s or a newer one of its major is not on PATH (found %s)" % (pin, installed))

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="openspec-contract-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ws = Path(self.tmp)
        shutil.copytree(str(REPO / "openspec" / "schemas"), str(self.ws / "openspec" / "schemas"))
        shutil.copy2(str(REPO / "openspec" / "config.yaml"), str(self.ws / "openspec" / "config.yaml"))
        (self.ws / "openspec" / "changes").mkdir()
        (self.ws / "openspec" / "specs").mkdir()
        self.change = self.ws / "openspec" / "changes" / "add-greeting"

    def cli(self, *args):
        res = subprocess.run(["openspec"] + list(args), cwd=str(self.ws), stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True,
                             timeout=120, env=dict(os.environ, DO_NOT_TRACK="1", NO_COLOR="1"))
        return res.returncode, res.stdout, res.stderr

    def ok(self, *args):
        code, out, err = self.cli(*args)
        self.assertEqual(0, code, "openspec %s failed:\n%s\n%s" % (" ".join(args), out, err))
        return out

    def js(self, *args):
        return json.loads(self.ok(*(list(args) + ["--json"])))

    def new_change(self, spec=True, plan=True, path="greeting"):
        self.ok("new", "change", "add-greeting")
        if spec:
            target = self.change / "specs" / path / "spec.md"
            target.parent.mkdir(parents=True)
            target.write_text(spec_from_template())
        if plan:
            (self.change / "plan.md").write_text(PLAN)

    def test_schema_is_valid(self):
        self.ok("schema", "validate", "spec-plan")

    def test_new_change_records_the_schema_of_the_config(self):
        self.new_change(spec=False, plan=False)
        self.assertIn("schema: spec-plan", (self.change / ".openspec.yaml").read_text())

    def test_status_lists_specs_then_plan(self):
        self.new_change(spec=False, plan=False)
        status = self.js("status", "--change", "add-greeting")
        self.assertEqual(["specs", "plan"], [a["id"] for a in status["artifacts"]])
        self.assertEqual(["ready", "blocked"], [a["status"] for a in status["artifacts"]])
        self.assertEqual(["plan"], status["applyRequires"])

    def test_status_reports_done_once_the_files_exist(self):
        self.new_change()
        status = self.js("status", "--change", "add-greeting")
        self.assertEqual(["done", "done"], [a["status"] for a in status["artifacts"]])

    def test_artifact_instructions_carry_the_template_the_rules_and_the_context(self):
        self.new_change(plan=False)
        for artifact, template in (("specs", "spec.md"), ("plan", "plan.md")):
            data = self.js("instructions", artifact, "--change", "add-greeting")
            for key in ("instruction", "template", "context", "resolvedOutputPath", "dependencies"):
                self.assertIn(key, data, artifact)
            self.assertEqual((SCHEMA / "templates" / template).read_text().strip(), data["template"].strip())
            self.assertIn("repos.json", data["context"])
        self.assertEqual(["specs"], [d["id"] for d in data["dependencies"]])
        self.assertIn("openspec-tracker-sync", " ".join(data["rules"]))
        self.assertTrue(data["resolvedOutputPath"].endswith("add-greeting/plan.md"))

    def test_a_spec_written_from_the_template_passes_strict_validation(self):
        self.new_change()
        self.ok("validate", "add-greeting", "--type", "change", "--strict")

    def test_lowercase_scenario_keywords_fail_strict_validation(self):
        """Why the template and the schema instruction ask for GIVEN, WHEN and THEN in capitals."""
        self.new_change()
        spec = self.change / "specs" / "greeting" / "spec.md"
        spec.write_text(spec.read_text().replace("GIVEN", "Given").replace("WHEN", "when").replace("THEN", "then"))
        code, out, err = self.cli("validate", "add-greeting", "--type", "change", "--strict")
        self.assertNotEqual(0, code, out + err)

    def test_apply_instructions_track_the_checkboxes_of_plan_md(self):
        self.new_change()
        data = self.js("instructions", "apply", "--change", "add-greeting")
        self.assertEqual("ready", data["state"])
        self.assertEqual({"total": 3, "complete": 1, "remaining": 2}, data["progress"])
        self.assertEqual({"specs", "plan"}, set(data["contextFiles"]))
        self.assertIn("Implement only the first phase with unchecked tasks", data["instruction"])
        self.assertIn("openspec-tracker-sync", " ".join(data["operationGuidance"]))
        self.assertIn("repos.json", data["context"])

    def test_apply_is_blocked_without_a_plan(self):
        self.new_change(plan=False)
        self.assertEqual("blocked", self.js("instructions", "apply", "--change", "add-greeting")["state"])

    def test_apply_is_all_done_when_every_task_is_checked(self):
        self.new_change()
        plan = self.change / "plan.md"
        plan.write_text(plan.read_text().replace("- [ ]", "- [x]"))
        self.assertEqual("all_done", self.js("instructions", "apply", "--change", "add-greeting")["state"])

    def test_list_counts_the_tasks_of_plan_md(self):
        self.new_change()
        changes = self.js("list")["changes"]
        self.assertEqual([("add-greeting", 1, 3)], [(c["name"], c["completedTasks"], c["totalTasks"]) for c in changes])

    def test_archive_merges_the_delta_and_moves_the_change(self):
        for path in ("greeting", "shop/greeting"):
            with self.subTest(path=path):
                self.new_change(path=path)
                self.ok("archive", "add-greeting", "--yes")
                main = self.ws / "openspec" / "specs" / path / "spec.md"
                self.assertIn("### Requirement: Greet by name", main.read_text())
                self.assertFalse(self.change.exists())
                archived = list((self.ws / "openspec" / "changes" / "archive").glob("*-add-greeting"))
                self.assertEqual(1, len(archived))
                self.assertIn(path, self.ok("list", "--specs"))
                self.ok("validate", "--all", "--strict")
                shutil.rmtree(str(archived[0]))
                shutil.rmtree(str(self.ws / "openspec" / "specs" / path.split("/")[0]))

    def test_archive_replaces_a_modified_requirement(self):
        self.new_change()
        self.ok("archive", "add-greeting", "--yes")
        self.ok("new", "change", "change-greeting")
        delta = self.ws / "openspec" / "changes" / "change-greeting" / "specs" / "greeting" / "spec.md"
        delta.parent.mkdir(parents=True)
        delta.write_text("## MODIFIED Requirements\n\n### Requirement: Greet by name\n"
                         "The system SHALL return a greeting that contains the given name and the time of day.\n\n"
                         "#### Scenario: Known name\n"
                         '- GIVEN the name "Ana" at 09:00, WHEN a greeting is requested, THEN the response is "Good morning, Ana"\n')
        (delta.parent.parent.parent / "plan.md").write_text(PLAN.replace("- [ ]", "- [x]"))
        self.ok("validate", "change-greeting", "--type", "change", "--strict")
        self.ok("archive", "change-greeting", "--yes")
        main = (self.ws / "openspec" / "specs" / "greeting" / "spec.md").read_text()
        self.assertIn("Good morning, Ana", main)
        self.assertNotIn("Hello, Ana", main)
        self.assertEqual(1, main.count("### Requirement: Greet by name"))

    def test_the_x_tracker_key_of_the_config_draws_no_warning(self):
        self.new_change()
        code, out, err = self.cli("validate", "--all", "--strict")
        self.assertEqual(0, code, out + err)
        self.assertNotIn("x-tracker", out + err)


if __name__ == "__main__":
    unittest.main()
