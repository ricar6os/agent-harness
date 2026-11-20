"""Tests for scripts/check.py: one green case and one red case per kind of violation."""
import contextlib
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("check", str(REPO / "scripts" / "check.py"))
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)

def write(root, rel, text=""):
    path = Path(root) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def git(root, *args):
    subprocess.run(["git", "-C", str(root)] + list(args), check=True,
                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)


OPENCODE_PLUGIN = """// scripts/guard.py is asked before every tool call
import { spawnSync } from "node:child_process"
const script = "../../scripts/guard.py"
export default {
  id: "guardrails",
  async setup(ctx) {
    await ctx.tool.hook("execute.before", (event) => {
      spawnSync("python3", [script, "--agent", "opencode"])
    })
  },
}
"""


def write_guard_wiring(root):
    script = write(root, "scripts/guard.py", "#!/usr/bin/env python3\n")
    script.chmod(0o755)
    for rel, agent in ((".claude/settings.json", "claude"), (".codex/hooks.json", "codex")):
        write(root, rel, json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash|apply_patch", "hooks": [
            {"type": "command", "command": 'python3 "$ROOT/scripts/guard.py" --agent %s' % agent}]}]}}))
    write(root, ".opencode/plugins/guard.js", OPENCODE_PLUGIN)


def make_workspace(parent):
    root = Path(parent) / "ws"
    root.mkdir()
    write(root, "repos.json", json.dumps({
        "org": "acme", "root": "repos",
        "repos": [
            {"name": "api", "url": "git@github.com:acme/api.git", "branch": "main", "products": ["shop"]},
            {"name": "web", "url": "git@github.com:acme/web.git", "products": ["shop"]},
        ]}))
    url = "https://mcp.example.com/mcp"
    write_guard_wiring(root)
    write(root, ".mcp.json", json.dumps({"mcpServers": {"tracker": {"type": "http", "url": url}}}))
    write(root, ".codex/config.toml", '# comment\n[mcp_servers.tracker]\nurl = "%s"\n' % url)
    write(root, "opencode.json", json.dumps({"mcp": {"tracker": {"type": "remote", "url": url}}}))
    write(root, ".agents/skills/demo/SKILL.md", "---\nname: demo\ndescription: Demo skill.\n---\nBody\n")
    link = root / ".claude" / "skills" / "demo" / "SKILL.md"
    link.parent.mkdir(parents=True)
    os.symlink("../../../.agents/skills/demo/SKILL.md", str(link))
    write(root, "openspec/changes/add-x/.openspec.yaml",
          "schema: spec-plan\nx-product: shop\nx-linear-project:\n  id: p-1\n  url: https://linear.app/p-1\nx-linear-sync-version: 2\n")
    write(root, "openspec/changes/add-x/specs/shop/orders/spec.md", "## ADDED Requirements\n")
    write(root, "openspec/changes/add-x/plan.md", "# Plan\n")
    write(root, "openspec/specs/shop/orders/spec.md", "# orders\n")
    write(root, "openspec/config.yaml", "schema: spec-plan\nx-tracker: linear\n")
    write(root, "env/README.md", "env\n")
    git(root, "init", "-q")
    git(root, "add", "-A")
    return root


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="check-test-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.ws = make_workspace(self.tmp)

    def rule(self, rule_id, **kwargs):
        found = [r for r in check.RULES if r.id == rule_id][0]
        return found.func(self.ws, **kwargs)

    def assertViolation(self, violations, rule_id, fragment):
        self.assertTrue(any(v.rule == rule_id and fragment in v.message for v in violations),
                        "no %s violation containing %r in:\n%s" % (rule_id, fragment, "\n".join(v.render() for v in violations)))

    def assertClean(self, violations):
        self.assertEqual([], [v.render() for v in violations])


class ManifestTests(Base):
    def edit(self, fn):
        path = self.ws / "repos.json"
        data = json.loads(path.read_text())
        fn(data)
        path.write_text(json.dumps(data))
        return self.rule("manifest")

    def test_green(self):
        self.assertClean(self.rule("manifest"))

    def test_missing_file(self):
        (self.ws / "repos.json").unlink()
        self.assertViolation(self.rule("manifest"), "manifest", "file not found")

    def test_invalid_json(self):
        write(self.ws, "repos.json", "{nope")
        self.assertViolation(self.rule("manifest"), "manifest", "not valid JSON")

    def test_top_level_not_object(self):
        write(self.ws, "repos.json", "[]")
        self.assertViolation(self.rule("manifest"), "manifest", "top level must be an object")

    def test_unknown_top_level_key(self):
        self.assertViolation(self.edit(lambda d: d.update(extra=1)), "manifest", 'unknown top-level key "extra"')

    def test_org_empty(self):
        self.assertViolation(self.edit(lambda d: d.update(org="")), "manifest", '"org" must be a non-empty string')

    def test_root_with_dotdot(self):
        self.assertViolation(self.edit(lambda d: d.update(root="../x")), "manifest", '"root" must be a non-empty relative path')

    def test_repos_not_list(self):
        self.assertViolation(self.edit(lambda d: d.update(repos={})), "manifest", '"repos" must be a list')

    def test_product_typo_names_the_key(self):
        def fn(d):
            d["repos"][1]["product"] = ["shop"]
        vs = self.edit(fn)
        self.assertViolation(vs, "manifest", 'repos[1] "web": unknown key "product". Use "products"')

    def test_other_unknown_key(self):
        self.assertViolation(self.edit(lambda d: d["repos"][0].update(tags=[])), "manifest", 'unknown key "tags"')

    def test_repo_not_object(self):
        self.assertViolation(self.edit(lambda d: d["repos"].append("x")), "manifest", "must be an object")

    def test_name_and_url_required(self):
        def fn(d):
            d["repos"][0]["name"] = ""
            d["repos"][1]["url"] = 3
        vs = self.edit(fn)
        self.assertViolation(vs, "manifest", '"name" must be a non-empty string')
        self.assertViolation(vs, "manifest", '"url" must be a non-empty string')

    def test_branch_and_path_non_empty(self):
        def fn(d):
            d["repos"][0]["branch"] = ""
            d["repos"][1]["path"] = ""
        vs = self.edit(fn)
        self.assertViolation(vs, "manifest", '"branch" must be a non-empty string')
        self.assertViolation(vs, "manifest", '"path" must be a non-empty string')

    def test_description_must_be_string_but_may_be_empty(self):
        self.assertClean(self.edit(lambda d: d["repos"][0].update(description="")))
        self.assertViolation(self.edit(lambda d: d["repos"][0].update(description=1)), "manifest", '"description" must be a string')

    def test_check_command_is_allowed(self):
        self.assertClean(self.edit(lambda d: d["repos"][0].update(check="uv run poe check")))

    def test_check_must_be_a_non_empty_single_line_string(self):
        for value in ("", "  ", 3, ["make"], None, "a\nb", "a\rb"):
            vs = self.edit(lambda d: d["repos"][0].update(check=value))
            self.assertViolation(vs, "manifest", '"check" must be a non-empty single-line string')

    def test_check_rejects_control_characters(self):
        for value in ("a\tb", "a\x01b", "a\x7fb"):
            vs = self.edit(lambda d: d["repos"][0].update(check=value))
            self.assertViolation(vs, "manifest", '"check" must be a non-empty single-line string')

    def test_path_and_default_path_must_be_a_direct_child(self):
        vs = self.edit(lambda d: d["repos"][0].update(path="grp/sub"))
        self.assertViolation(vs, "manifest", "clones live directly under the repos directory")
        vs = self.edit(lambda d: d["repos"][0].update(name="grp/sub"))
        self.assertViolation(vs, "manifest", "clones live directly under the repos directory")

    def test_path_with_dot_slash_or_trailing_slash_is_a_direct_child(self):
        self.assertClean(self.edit(lambda d: d["repos"][0].update(path="./api-dir/")))

    def test_products_empty(self):
        vs = self.edit(lambda d: d["repos"][0].update(products=[]))
        self.assertViolation(vs, "manifest", "Omit \"products\" for a repo shared by every product")

    def test_products_not_list(self):
        self.assertViolation(self.edit(lambda d: d["repos"][0].update(products="shop")), "manifest", "must be a list of product slugs")

    def test_products_bad_slug(self):
        self.assertViolation(self.edit(lambda d: d["repos"][0].update(products=["Shop_1"])), "manifest", "is not a slug")

    def test_duplicate_name(self):
        self.assertViolation(self.edit(lambda d: d["repos"][1].update(name="api")), "manifest", 'name "api" is used by')

    def test_duplicate_effective_path(self):
        vs = self.edit(lambda d: d["repos"][1].update(path="api"))
        self.assertViolation(vs, "manifest", 'path "api" is used by')

    def test_duplicate_path_after_normalization(self):
        def fn(d):
            d["repos"] = [
                {"name": "api", "url": "u"},
                {"name": "x", "url": "u", "path": "./api"},
                {"name": "y", "url": "u", "path": "api/"},
            ]
        vs = self.edit(fn)
        self.assertViolation(vs, "manifest", 'path "api" is used by repos[0, 1, 2]')

    def test_distinct_paths_after_normalization_pass(self):
        def fn(d):
            d["repos"] = [{"name": "api", "url": "u"}, {"name": "x", "url": "u", "path": "./web/"}]
        self.assertClean(self.edit(fn))

    def test_root_with_dot_slash_prefix_is_fine(self):
        self.assertClean(self.edit(lambda d: d.update(root="./repos/")))

    def test_root_that_normalizes_to_dot_or_is_absolute(self):
        for value in (".", "./", "/abs", "a/../.."):
            vs = self.edit(lambda d: d.update(root=value))
            self.assertViolation(vs, "manifest", '"root" must be a non-empty relative path')

    def test_repo_path_absolute_dot_or_escaping(self):
        for value in ("/abs/api", ".", "./", "a/..", "../out", "x/../../out"):
            vs = self.edit(lambda d: d["repos"][0].update(path=value))
            self.assertViolation(vs, "manifest", "must be a relative path inside the clones directory")

    def test_repo_name_escaping_is_reported(self):
        vs = self.edit(lambda d: d["repos"][0].update(name="../x"))
        self.assertViolation(vs, "manifest", "must be a relative path inside the clones directory")

    def test_normalize_rel(self):
        n = check.normalize_rel
        self.assertEqual("repos", n("./repos/"))
        self.assertEqual("a/b", n("a//b/./"))
        self.assertEqual("b", n("a/../b"))
        for bad in ("", ".", "./", "/x", "..", "../x", "a/..", "a/../..", None, 3):
            self.assertIsNone(n(bad), bad)


class ChangeProductTests(Base):
    def test_green(self):
        self.assertClean(self.rule("change-product"))

    def test_missing_openspec_yaml(self):
        (self.ws / "openspec/changes/add-x/.openspec.yaml").unlink()
        self.assertViolation(self.rule("change-product"), "change-product", "missing .openspec.yaml")

    def test_no_product(self):
        write(self.ws, "openspec/changes/add-x/.openspec.yaml", "schema: spec-plan\n")
        self.assertViolation(self.rule("change-product"), "change-product", "no top-level `x-product: <slug>`")

    def test_unknown_product(self):
        write(self.ws, "openspec/changes/add-x/.openspec.yaml", 'x-product: "billing"\n')
        self.assertViolation(self.rule("change-product"), "change-product", 'product "billing" is not in repos.json')

    def without_products(self):
        write(self.ws, "repos.json", json.dumps({"org": "a", "repos": [
            {"name": "api", "url": "git@github.com:acme/api.git"}]}))
        write(self.ws, "openspec/changes/add-x/.openspec.yaml", "schema: spec-plan\n")
        shutil.rmtree(str(self.ws / "openspec/changes/add-x/specs/shop"))
        shutil.rmtree(str(self.ws / "openspec/specs/shop"))

    def test_without_products_specs_start_with_capability(self):
        self.without_products()
        write(self.ws, "openspec/changes/add-x/specs/orders/spec.md")
        write(self.ws, "openspec/specs/orders/spec.md")
        self.assertClean(self.rule("change-product"))

    def test_without_products_openspec_yaml_is_optional(self):
        self.without_products()
        (self.ws / "openspec/changes/add-x/.openspec.yaml").unlink()
        self.assertClean(self.rule("change-product"))

    def test_without_products_x_product_is_reported(self):
        self.without_products()
        write(self.ws, "openspec/changes/add-x/.openspec.yaml", "x-product: shop\n")
        self.assertViolation(self.rule("change-product"), "change-product", "repos.json declares no products. Remove the key")

    def test_without_products_product_level_spec_is_reported(self):
        self.without_products()
        write(self.ws, "openspec/changes/add-x/specs/shop/orders/spec.md")
        write(self.ws, "openspec/specs/shop/orders/spec.md")
        vs = self.rule("change-product")
        self.assertViolation(vs, "change-product", "delta spec must sit at specs/<capability>/spec.md")
        self.assertViolation(vs, "change-product", "main spec must sit at openspec/specs/<capability>/spec.md")

    def test_delta_spec_depth(self):
        write(self.ws, "openspec/changes/add-x/specs/orders/spec.md")
        self.assertViolation(self.rule("change-product"), "change-product", "delta spec must sit at specs/<product>/<capability>/spec.md")

    def test_delta_spec_other_product(self):
        write(self.ws, "openspec/changes/add-x/specs/billing/invoices/spec.md")
        self.assertViolation(self.rule("change-product"), "change-product", 'under product "billing" but the change is product "shop"')

    def test_main_spec_depth(self):
        write(self.ws, "openspec/specs/orders/spec.md")
        self.assertViolation(self.rule("change-product"), "change-product", "main spec must sit at openspec/specs/<product>/<capability>/spec.md")

    def test_main_spec_unknown_slug(self):
        write(self.ws, "openspec/specs/billing/invoices/spec.md")
        self.assertViolation(self.rule("change-product"), "change-product", 'main spec directory "billing" is not a product')

    def test_legacy_keys_each_reported_with_replacement(self):
        write(self.ws, "openspec/changes/add-x/.openspec.yaml",
              "schema: spec-plan\nx-product: shop\nlinear_project:\n  id: p-9\nlinear_sync_version: 2\n")
        vs = self.rule("change-product")
        self.assertEqual(2, len(vs), vs)
        self.assertTrue(any("`linear_project`" in v.message and "`x-linear-project`" in v.message for v in vs))
        self.assertTrue(any("`linear_sync_version`" in v.message and "`x-linear-sync-version`" in v.message for v in vs))
        self.assertTrue(all("OpenSpec 2 rejects unknown keys" in v.message for v in vs))

    def test_legacy_product_reports_only_migration(self):
        write(self.ws, "openspec/changes/add-x/.openspec.yaml", "schema: spec-plan\nproduct: shop\n")
        vs = self.rule("change-product")
        self.assertEqual(1, len(vs), vs)
        self.assertIn("`product` is the old key name. Rename it to `x-product`", vs[0].message)

    def test_legacy_and_new_product_both_present(self):
        write(self.ws, "openspec/changes/add-x/.openspec.yaml", "x-product: shop\nproduct: shop\n")
        vs = self.rule("change-product")
        self.assertEqual(1, len(vs), vs)
        self.assertIn("Rename it to `x-product`", vs[0].message)

    def test_archived_legacy_keys_are_history(self):
        write(self.ws, "openspec/changes/archive/2026-01-01-old/.openspec.yaml",
              "product: shop\nlinear_project:\n  id: p-7\nlinear_sync_version: 2\n")
        self.assertClean(self.rule("change-product"))

    def test_linear_project_shared_with_archived_legacy_change(self):
        write(self.ws, "openspec/changes/archive/2026-01-01-old/.openspec.yaml", "product: shop\nlinear_project:\n  id: p-1\n")
        vs = [v for v in self.rule("change-product") if "p-1" in v.message]
        self.assertEqual(1, len(vs))
        self.assertIn("x-linear-project.id p-1", vs[0].message)

    def test_linear_project_shared_with_archived_change(self):
        write(self.ws, "openspec/changes/archive/2026-01-01-old/.openspec.yaml", "x-product: shop\nx-linear-project:\n  id: p-1\n")
        vs = [v for v in self.rule("change-product") if "p-1" in v.message]
        self.assertEqual(1, len(vs))
        self.assertIn("add-x", vs[0].message)
        self.assertIn("2026-01-01-old", vs[0].message)

    def test_distinct_linear_projects_pass(self):
        write(self.ws, "openspec/changes/archive/old/.openspec.yaml", "x-product: shop\nx-linear-project:\n  id: p-2\n")
        self.assertClean(self.rule("change-product"))

    def test_quoted_keys_are_keys(self):
        write(self.ws, "openspec/changes/add-x/.openspec.yaml",
              '"x-product": shop\n\'x-linear-project\':\n  "id": p-3\n  \'url\': https://h/p\n')
        self.assertClean(self.rule("change-product"))
        parsed = check.parse_simple_yaml('"x-product": shop\n\'n\':\n  "id": q\n')
        self.assertEqual({"x-product": "shop", "n": {"id": "q"}}, parsed)

    def test_quoted_legacy_key_gets_the_migration_message(self):
        write(self.ws, "openspec/changes/add-x/.openspec.yaml", "'product': shop\n")
        vs = self.rule("change-product")
        self.assertEqual(1, len(vs), vs)
        self.assertIn("`product` is the old key name. Rename it to `x-product`", vs[0].message)

    def test_yaml_parser(self):
        parsed = check.parse_simple_yaml("a: 'x'\nb: y # c\nn:\n  id: \"q\"\n  url: https://h/p\n")
        self.assertEqual({"a": "x", "b": "y", "n": {"id": "q", "url": "https://h/p"}}, parsed)


class TrackerTests(Base):
    def test_green(self):
        self.assertClean(self.rule("tracker"))

    def test_each_tracker_is_valid(self):
        for value in ("linear", "github", "none", "'none'  # comment"):
            write(self.ws, "openspec/config.yaml", "schema: spec-plan\nx-tracker: %s\n" % value)
            self.assertClean(self.rule("tracker"))

    def test_missing(self):
        write(self.ws, "openspec/config.yaml", "schema: spec-plan\n")
        self.assertViolation(self.rule("tracker"), "tracker", "no top-level `x-tracker:`")

    def test_unknown(self):
        write(self.ws, "openspec/config.yaml", "schema: spec-plan\nx-tracker: jira\n")
        vs = self.rule("tracker")
        self.assertViolation(vs, "tracker", "`x-tracker: jira` is not a tracker")
        self.assertEqual(2, vs[0].line)

    def test_indented_key_is_not_top_level(self):
        write(self.ws, "openspec/config.yaml", "schema: spec-plan\nrules:\n  x-tracker: linear\n")
        self.assertViolation(self.rule("tracker"), "tracker", "no top-level")

    def test_no_openspec_config(self):
        (self.ws / "openspec/config.yaml").unlink()
        self.assertClean(self.rule("tracker"))


class McpParityTests(Base):
    def test_green(self):
        self.assertClean(self.rule("mcp-parity"))

    def test_no_servers_anywhere_passes(self):
        for rel in (".mcp.json", ".codex/config.toml", "opencode.json"):
            (self.ws / rel).unlink()
        self.assertClean(self.rule("mcp-parity"))

    def test_server_missing_in_one_file(self):
        write(self.ws, "opencode.json", json.dumps({"mcp": {}}))
        vs = self.rule("mcp-parity")
        self.assertViolation(vs, "mcp-parity", 'server "tracker" is declared in .mcp.json, .codex/config.toml but not in opencode.json')
        self.assertEqual(["opencode.json"], [v.path for v in vs])

    def test_file_missing(self):
        (self.ws / ".codex/config.toml").unlink()
        vs = self.rule("mcp-parity")
        self.assertEqual([".codex/config.toml"], [v.path for v in vs])

    def test_extra_server_in_one_file(self):
        write(self.ws, ".mcp.json", json.dumps({"mcpServers": {"tracker": {"url": "https://mcp.example.com/mcp"}, "extra": {}}}))
        vs = self.rule("mcp-parity")
        self.assertEqual(2, len([v for v in vs if '"extra"' in v.message]))

    def test_url_mismatch(self):
        write(self.ws, ".codex/config.toml", '[mcp_servers.tracker]\nurl = "https://other.example.com/mcp"\n')
        self.assertViolation(self.rule("mcp-parity"), "mcp-parity", "has different urls")

    def test_quoted_toml_name_and_subtable(self):
        write(self.ws, ".codex/config.toml",
              '[mcp_servers."tracker"]\nurl = "https://mcp.example.com/mcp"\n\n[mcp_servers.tracker.env]\nurl = "ignored"\n')
        self.assertClean(self.rule("mcp-parity"))

    def test_invalid_json(self):
        write(self.ws, ".mcp.json", "{")
        self.assertViolation(self.rule("mcp-parity"), "mcp-parity", "not valid JSON")

    TOML_FORMS = {
        "table": '[mcp_servers.linear-server]\nurl = "U"\n',
        "quoted table": '[mcp_servers."linear-server"]\nurl = "U"\n',
        "table with comment": "[ mcp_servers . linear-server ] # c\nurl = 'U' # c\n",
        "inline table under [mcp_servers]": '[mcp_servers]\nlinear-server = { url = "U" }\n',
        "quoted inline table": '[mcp_servers]\n"linear-server" = { type = "http", url = "U" }\n',
        "dotted key at top level": 'mcp_servers.linear-server.url = "U"\n',
        "quoted dotted key at top level": 'mcp_servers."linear-server".url = "U"\n',
        "dotted key under [mcp_servers]": '[mcp_servers]\nlinear-server.url = "U"\n',
        "inline mcp_servers": 'mcp_servers = { linear-server = { url = "U" } }\n',
        "sub-table beside url": '[mcp_servers.linear-server]\nurl = "U"\n[mcp_servers.linear-server.env]\nurl = "x"\n',
    }

    def test_toml_forms_fallback_parser(self):
        for name, text in self.TOML_FORMS.items():
            self.assertEqual({"linear-server": "U"}, check.parse_codex_servers_lines(text), name)

    def test_toml_forms_agree_with_tomllib(self):
        if check.tomllib is None:
            self.assertEqual({}, check.parse_codex_servers_lines("[other]\nx = 1\n"))
            return
        for name, text in self.TOML_FORMS.items():
            self.assertEqual(check.parse_codex_servers_lines(text), check.parse_codex_servers_tomllib(text), name)
        extra = '[mcp_servers.a]\ncommand = "x"\n[mcp_servers.b.env]\nK = "v"\n[[other]]\nurl = "no"\n[x]\nurl = "no"\n'
        self.assertEqual(check.parse_codex_servers_lines(extra), check.parse_codex_servers_tomllib(extra))
        self.assertEqual({"a": None, "b": None}, check.parse_codex_servers_lines(extra))

    UNSUPPORTED_TOML = {
        "url inside a multi-line basic string": '[mcp_servers.a]\nurl = "U"\nnote = """\nurl = "other"\n"""\n',
        "url inside a multi-line literal string": "[mcp_servers.a]\nnote = \'\'\'\nurl = 'other'\n\'\'\'\n",
        "array of tables": '[[mcp_servers.a]]\nurl = "U"\n',
        "escape in a url": '[mcp_servers.a]\nurl = "https://h/\\"x"\n',
        "escape in a server name": '[mcp_servers."a\\"b"]\nurl = "U"\n',
    }

    def test_fallback_parser_refuses_what_it_does_not_implement(self):
        for name, text in self.UNSUPPORTED_TOML.items():
            with self.subTest(name):
                with self.assertRaises(check.UnsupportedToml):
                    check.parse_codex_servers_lines(text)

    def test_fallback_parser_ignores_triple_quotes_in_comments(self):
        for text in ('# use """ for long strings\n[mcp_servers.a]\nurl = "U"\n',
                     "[mcp_servers.a]\nurl = \"U\"  # not \'\'\'multi-line\n",
                     '[mcp_servers.a] # """\nurl = "U"\n'):
            with self.subTest(text):
                self.assertEqual({"a": "U"}, check.parse_codex_servers_lines(text))
        with self.assertRaises(check.UnsupportedToml):   # a real one is still refused, comment or not
            check.parse_codex_servers_lines('# note\n[mcp_servers.a]\nurl = "U"\nx = """\ny\n"""  # c\n')
        self.assertEqual('x = "a # b" \'#\' ', check.strip_toml_comments('x = "a # b" \'#\' # c \'\'\''))   # `#` in a string stays

    def test_fallback_parser_accepts_escapes_it_does_not_need(self):
        text = '[mcp_servers.a]\nurl = "U"\ncommand = "C:\\\\x"\n'
        self.assertEqual({"a": "U"}, check.parse_codex_servers_lines(text))

    def test_without_tomllib_unsupported_toml_skips_or_violates(self):
        for name, text in self.UNSUPPORTED_TOML.items():
            write(self.ws, ".codex/config.toml", text)
            with self.subTest(name), mock.patch.object(check, "tomllib", None):
                with self.assertRaises(check.Skip) as ctx:
                    self.rule("mcp-parity")
                self.assertIn("Python 3.11+", str(ctx.exception))
                vs = self.rule("mcp-parity", require_tools=True)
                self.assertViolation(vs, "mcp-parity", "Python 3.11+")
                self.assertEqual([".codex/config.toml"], [v.path for v in vs])

    def test_the_same_files_are_parsed_when_tomllib_exists(self):
        write(self.ws, ".codex/config.toml", '[mcp_servers.tracker]\nurl = "https://mcp.example.com/mcp"\nnote = """\nurl = "x"\n"""\n')
        if check.tomllib is None:
            with self.assertRaises(check.Skip):
                self.rule("mcp-parity")
        else:
            self.assertClean(self.rule("mcp-parity"))

    def test_every_toml_form_passes_parity(self):
        for name, text in self.TOML_FORMS.items():
            write(self.ws, ".mcp.json", json.dumps({"mcpServers": {"linear-server": {"url": "U"}}}))
            write(self.ws, "opencode.json", json.dumps({"mcp": {"linear-server": {"url": "U"}}}))
            write(self.ws, ".codex/config.toml", text)
            self.assertClean(self.rule("mcp-parity"))

    def test_invalid_toml_is_a_violation_naming_the_file(self):
        write(self.ws, ".codex/config.toml", "[mcp_servers.tracker\nurl = \n")
        vs = self.rule("mcp-parity")
        if check.tomllib is None:
            self.assertTrue(all(v.path != ".codex/config.toml" or "TOML" not in v.message for v in vs))
        else:
            self.assertEqual([".codex/config.toml"], [v.path for v in vs if "not valid TOML" in v.message])


class SkillExposureTests(Base):
    def test_green(self):
        self.assertClean(self.rule("skill-exposure"))

    def test_name_mismatch(self):
        write(self.ws, ".agents/skills/demo/SKILL.md", "---\nname: other\ndescription: d\n---\n")
        self.assertViolation(self.rule("skill-exposure"), "skill-exposure", 'frontmatter name is "other" but the directory is "demo"')

    def test_trailing_yaml_comment_is_not_part_of_the_name(self):
        write(self.ws, ".agents/skills/demo/SKILL.md", "---\nname: demo # x\ndescription: Demo skill. # y\n---\nBody\n")
        self.assertClean(self.rule("skill-exposure"))

    def test_hash_inside_quotes_is_content(self):
        lines = ['name: "de#mo" # c', "name: 'a #b'", "name: a#b", "name: # only a comment"]
        got = [check.frontmatter_value([l], "name") for l in lines]
        self.assertEqual(["de#mo", "a #b", "a#b", ""], got)

    def test_missing_description(self):
        write(self.ws, ".agents/skills/demo/SKILL.md", "---\nname: 'demo'\ndescription:\n---\n")
        self.assertViolation(self.rule("skill-exposure"), "skill-exposure", "no description")

    def test_block_description_is_fine(self):
        write(self.ws, ".agents/skills/demo/SKILL.md", "---\nname: demo\ndescription: >\n  Long text.\n---\n")
        self.assertClean(self.rule("skill-exposure"))

    def test_no_frontmatter(self):
        write(self.ws, ".agents/skills/demo/SKILL.md", "Body only\n")
        self.assertViolation(self.rule("skill-exposure"), "skill-exposure", "no frontmatter")

    def test_not_exposed_prints_ln_command(self):
        write(self.ws, ".agents/skills/new/SKILL.md", "---\nname: new\ndescription: d\n---\n")
        self.assertViolation(self.rule("skill-exposure"), "skill-exposure",
                             "ln -s ../../../.agents/skills/new/SKILL.md .claude/skills/new/SKILL.md")

    def test_directory_symlink_and_real_file_are_exposed(self):
        write(self.ws, ".agents/skills/a/SKILL.md", "---\nname: a\ndescription: d\n---\n")
        os.symlink("../../.agents/skills/a", str(self.ws / ".claude/skills/a"))
        write(self.ws, ".agents/skills/b/SKILL.md", "---\nname: b\ndescription: d\n---\n")
        write(self.ws, ".claude/skills/b/SKILL.md", "---\nname: b\ndescription: d\n---\n")
        self.assertClean(self.rule("skill-exposure"))

    def test_claude_entry_without_canonical(self):
        write(self.ws, ".claude/skills/orphan/SKILL.md", "---\nname: orphan\ndescription: d\n---\n")
        self.assertViolation(self.rule("skill-exposure"), "skill-exposure", "no .agents/skills/orphan/SKILL.md, the canonical location")

    def test_broken_symlink(self):
        os.symlink("../../.agents/skills/gone", str(self.ws / ".claude/skills/gone"))
        vs = self.rule("skill-exposure")
        self.assertViolation(vs, "skill-exposure", "broken symlink")
        self.assertEqual(1, len(vs))

    def test_double_dash_entries_and_dotfiles_are_ignored(self):
        os.symlink("../../repos/api/.agents/skills/x", str(self.ws / ".claude/skills/api--x"))
        os.symlink("../../repos/api/.agents/skills/x", str(self.ws / ".agents/skills/api--x"))
        write(self.ws, ".agents/skills/foo--bar/SKILL.md", "no frontmatter\n")
        write(self.ws, ".agents/skills/.hidden/SKILL.md", "no frontmatter\n")
        self.assertClean(self.rule("skill-exposure"))

    def test_lock_key_without_skill(self):
        write(self.ws, "skills-lock.json", json.dumps({"version": 1, "skills": {"demo": {}, "ghost": {}}}))
        vs = self.rule("skill-exposure")
        self.assertViolation(vs, "skill-exposure", 'locked skill "ghost"')
        self.assertEqual(1, len(vs))


class TrackedSecretsTests(Base):
    def track(self, rel, text="x\n"):
        write(self.ws, rel, text)
        git(self.ws, "add", "-f", rel)

    def test_green(self):
        self.assertClean(self.rule("tracked-secrets", require_tools=False))

    def test_allowed_files_pass(self):
        self.track(".env.example")
        self.track("services/api/.env.template")
        self.track("env/.gitkeep")
        self.track("env/api/.gitkeep")
        self.assertClean(self.rule("tracked-secrets", require_tools=False))

    def test_tracked_env_file(self):
        self.track("env/api/.env", "SECRET=1\n")
        vs = self.rule("tracked-secrets", require_tools=False)
        self.assertViolation(vs, "tracked-secrets", "git rm --cached env/api/.env")
        self.assertEqual(1, len(vs))

    def test_tracked_repo_clone_file(self):
        self.track("repos/api/README.md")
        self.assertViolation(self.rule("tracked-secrets", require_tools=False), "tracked-secrets", "tracked file under repos/")

    def test_manifest_root_is_honoured(self):
        write(self.ws, "repos.json", json.dumps({"org": "a", "root": "clones", "repos": []}))
        self.track("clones/api/x.txt")
        self.assertViolation(self.rule("tracked-secrets", require_tools=False), "tracked-secrets", "tracked file under clones/")

    def test_manifest_root_with_dot_slash_is_normalized(self):
        write(self.ws, "repos.json", json.dumps({"org": "a", "root": "./repos/", "repos": []}))
        self.track("repos/api/secret.txt")
        self.assertViolation(self.rule("tracked-secrets", require_tools=False), "tracked-secrets", "tracked file under repos/")

    def test_dotenv_files_anywhere(self):
        self.track("services/api/.env")
        self.track("services/api/.env.production")
        vs = self.rule("tracked-secrets", require_tools=False)
        self.assertViolation(vs, "tracked-secrets", "`git rm --cached services/api/.env`")
        self.assertViolation(vs, "tracked-secrets", "git rm --cached services/api/.env.production")

    def test_dotenv_name_is_case_insensitive(self):
        self.track("services/api/.ENV")
        self.track("services/api/.Env.Local")
        self.track("services/api/.ENV.EXAMPLE")
        vs = self.rule("tracked-secrets", require_tools=False)
        self.assertViolation(vs, "tracked-secrets", "git rm --cached services/api/.ENV`")
        self.assertViolation(vs, "tracked-secrets", "git rm --cached services/api/.Env.Local")
        self.assertEqual(2, len(vs))

    def test_not_a_git_work_tree_is_a_skip(self):
        shutil.rmtree(str(self.ws / ".git"))
        with mock.patch.object(check, "git_tracked", return_value=(False, "not a git work tree")):
            with self.assertRaises(check.Skip):
                self.rule("tracked-secrets", require_tools=True)

    def test_real_git_on_a_directory_that_is_not_a_work_tree_is_a_skip(self):
        parent = Path(tempfile.mkdtemp(prefix="check-nogit-"))
        self.addCleanup(shutil.rmtree, str(parent), True)
        plain = parent / "plain"
        plain.mkdir()
        write(plain, "repos.json", "{}")
        with mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": str(parent)}):
            tracked, problem = check.git_tracked(plain)
            self.assertIs(False, tracked)
            self.assertIn("is not a git work tree", problem)
            for require in (False, True):
                with self.assertRaises(check.Skip) as ctx:
                    check.check_tracked_secrets(plain, require_tools=require)
                self.assertIn("is not a git work tree", str(ctx.exception))


class GuardrailsTests(Base):
    def test_green(self):
        self.assertClean(self.rule("guardrails"))

    def test_missing_script(self):
        (self.ws / "scripts" / "guard.py").unlink()
        vs = self.rule("guardrails")
        self.assertViolation(vs, "guardrails", "missing. Restore it")
        self.assertEqual("scripts/guard.py", vs[0].path)

    def test_script_not_executable(self):
        (self.ws / "scripts" / "guard.py").chmod(0o644)
        self.assertViolation(self.rule("guardrails"), "guardrails", "chmod +x scripts/guard.py")

    def test_each_missing_config_file_is_reported_once(self):
        for rel in (".claude/settings.json", ".codex/hooks.json", ".opencode/plugins/guard.js"):
            with self.subTest(rel=rel):
                (self.ws / rel).rename(self.ws / (rel + ".off"))
                vs = self.rule("guardrails")
                self.assertEqual([rel], [v.path for v in vs])
                self.assertViolation(vs, "guardrails", "missing. Restore it")
                (self.ws / (rel + ".off")).rename(self.ws / rel)

    def test_config_that_does_not_parse(self):
        write(self.ws, ".claude/settings.json", "{not json")
        vs = self.rule("guardrails")
        self.assertEqual(1, len(vs))
        self.assertViolation(vs, "guardrails", "is not valid JSON")

    def test_config_that_does_not_call_the_script(self):
        write(self.ws, ".codex/hooks.json", json.dumps({"hooks": {"PreToolUse": []}}))
        write(self.ws, ".opencode/plugins/guard.js", "export default {}\n")
        vs = self.rule("guardrails")
        self.assertEqual([".codex/hooks.json", ".opencode/plugins/guard.js"], [v.path for v in vs])
        self.assertViolation(vs, "guardrails", "does not invoke scripts/guard.py")

    def test_a_mention_in_a_comment_is_not_a_plugin(self):
        write(self.ws, ".opencode/plugins/guard.js", "// see scripts/guard.py --agent opencode execute.before\nexport default {}\n")
        vs = self.rule("guardrails")
        self.assertEqual([".opencode/plugins/guard.js"], [v.path for v in vs])
        self.assertViolation(vs, "guardrails", "does not invoke scripts/guard.py")
        write(self.ws, ".opencode/plugins/guard.js", "/* scripts/guard.py --agent opencode execute.before */ export default {}\n")
        self.assertViolation(self.rule("guardrails"), "guardrails", "does not invoke")

    def test_plugin_needs_script_agent_flag_and_hook(self):
        full = OPENCODE_PLUGIN
        for what, text in (("script", full.replace("../../scripts/guard.py", "../../scripts/other.py")),
                           ("agent", full.replace('"opencode"', '"claude"')),
                           ("hook", full.replace("execute.before", "execute.after"))):
            with self.subTest(missing=what):
                write(self.ws, ".opencode/plugins/guard.js", text)
                self.assertViolation(self.rule("guardrails"), "guardrails", "does not invoke")

    def test_comment_markers_inside_strings_are_not_comments(self):
        write(self.ws, ".opencode/plugins/guard.js", OPENCODE_PLUGIN.replace(
            'const script = "../../scripts/guard.py"', 'const url = "https://x.example"\nconst script = "../../scripts/guard.py"'))
        self.assertClean(self.rule("guardrails"))

    def test_an_echo_in_a_stop_hook_is_not_a_guard(self):
        write(self.ws, ".codex/hooks.json", json.dumps({"hooks": {"Stop": [{"hooks": [
            {"type": "command", "command": "echo scripts/guard.py --agent codex"}]}]}}))
        vs = self.rule("guardrails")
        self.assertEqual([".codex/hooks.json"], [v.path for v in vs])
        self.assertViolation(vs, "guardrails", "PreToolUse")

    def test_hook_must_cover_the_shell_tool_and_name_the_agent(self):
        def hooks(matcher, command):
            return json.dumps({"hooks": {"PreToolUse": [{"matcher": matcher, "hooks": [{"type": "command", "command": command}]}]}})
        call = 'python3 scripts/guard.py --agent claude'
        for matcher, command, ok in (("Read|Edit", call, False), ("Bash", call.replace("claude", "codex"), False),
                                     ("Bash", "echo hi", False), ("Bash", call, True), ("*", call, True),
                                     ("Bash|Read", call, True)):
            with self.subTest(matcher=matcher, command=command):
                write(self.ws, ".claude/settings.json", hooks(matcher, command))
                self.assertEqual(ok, not self.rule("guardrails"))

    def test_mention_outside_hooks_does_not_count(self):
        write(self.ws, ".claude/settings.json", json.dumps({"note": "scripts/guard.py", "hooks": {}}))
        self.assertViolation(self.rule("guardrails"), "guardrails", "does not invoke")


class CliVersionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="check-pin-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.root = Path(self.tmp)

    def test_version_is_read_from_the_file(self):
        self.assertEqual((None, "openspec/cli-version not found"), check.pinned_openspec_version(self.root))
        write(self.root, "openspec/cli-version", " 3.4.5 \n\n")
        self.assertEqual(("3.4.5", None), check.pinned_openspec_version(self.root))

    def test_malformed_version_is_an_error(self):
        for text in ("v2.1.1\n", "2.1\n", "2.1.1 2.1.2\n", "\n"):
            write(self.root, "openspec/cli-version", text)
            version, err = check.pinned_openspec_version(self.root)
            self.assertIsNone(version, text)
            self.assertIn("must contain one version", err)

    def test_same_major_and_not_older_satisfies(self):
        for installed in ("2.1.1", "2.1.2", "2.2.0", "2.10.0", "2.1.1-beta.1"):
            self.assertTrue(check.version_satisfies(installed, "2.1.1"), installed)
        for installed in ("2.1.0", "2.0.9", "1.9.9", "3.0.0", "", None, "nonsense"):
            self.assertFalse(check.version_satisfies(installed, "2.1.1"), installed)


class OpenspecValidateTests(Base):
    def test_without_cli(self):
        with mock.patch.object(check.shutil, "which", return_value=None):
            with self.assertRaises(check.Skip):
                self.rule("openspec-validate", require_tools=False)
            vs = self.rule("openspec-validate", require_tools=True)
        self.assertViolation(vs, "openspec-validate", "openspec CLI is not installed")

    def pin(self, version):
        write(self.ws, "openspec/cli-version", version + "\n")

    def fake_run(self, code=0):
        return mock.Mock(return_value=mock.Mock(returncode=code, stdout="boom\n"))

    def test_older_or_other_major_cli_is_a_skip_or_a_violation(self):
        self.pin("9.9.9")
        for installed in ("9.9.8", "10.0.0", "1.13.0"):
            with mock.patch.object(check, "installed_openspec_version", return_value=installed), \
                    mock.patch.object(check.subprocess, "run", self.fake_run()) as run:
                with self.assertRaises(check.Skip) as ctx:
                    self.rule("openspec-validate", require_tools=False)
                self.assertIn("9.9.9 or a newer 9.x", str(ctx.exception))
                self.assertIn(installed, str(ctx.exception))
                self.assertIn("openspec/cli-version", str(ctx.exception))
                vs = self.rule("openspec-validate", require_tools=True)
                run.assert_not_called()
            self.assertEqual(["openspec-validate"], [v.rule for v in vs])
            self.assertIn("npm i -g @fission-ai/openspec@9.9.9", vs[0].message)

    def test_same_or_newer_cli_of_the_same_major_runs(self):
        self.pin("9.9.9")
        for installed in ("9.9.9", "9.10.0"):
            with mock.patch.object(check, "installed_openspec_version", return_value=installed), \
                    mock.patch.object(check.shutil, "which", return_value="/bin/openspec"), \
                    mock.patch.object(check.subprocess, "run", self.fake_run(1)) as run:
                vs = self.rule("openspec-validate", require_tools=False)
            run.assert_called_once()
            self.assertViolation(vs, "openspec-validate", "openspec validate --all --strict")

    def test_pinned_version_missing_cli(self):
        self.pin("9.9.9")
        with mock.patch.object(check.shutil, "which", return_value=None):
            with self.assertRaises(check.Skip) as ctx:
                self.rule("openspec-validate", require_tools=False)
            self.assertIn("found none", str(ctx.exception))
            self.assertViolation(self.rule("openspec-validate", require_tools=True), "openspec-validate", "found none")

    def test_invalid_pin_file_is_a_violation(self):
        self.pin("two")
        self.assertViolation(self.rule("openspec-validate", require_tools=False), "openspec-validate", "invalid")

    def test_without_pin_any_installed_cli_runs(self):
        with mock.patch.object(check, "installed_openspec_version", return_value="0.0.1"), \
                mock.patch.object(check.shutil, "which", return_value="/bin/openspec"), \
                mock.patch.object(check.subprocess, "run", self.fake_run(0)) as run:
            self.assertClean(self.rule("openspec-validate", require_tools=False))
        run.assert_called_once()

    def test_workspace_without_openspec_needs_no_cli(self):
        shutil.rmtree(str(self.ws / "openspec"))
        with mock.patch.object(check.shutil, "which", return_value=None), \
                mock.patch.object(check.subprocess, "run", self.fake_run(1)) as run:
            self.assertClean(self.rule("openspec-validate", require_tools=True))
            run.assert_not_called()

    def test_with_cli(self):
        if not shutil.which("openspec"):
            self.skipTest("openspec is not on PATH")
        shutil.rmtree(str(self.ws / "openspec/changes/add-x"))
        shutil.rmtree(str(self.ws / "openspec/specs/shop"))
        self.assertClean(self.rule("openspec-validate", require_tools=False))
        write(self.ws, "openspec/changes/bad/proposal.md", "nothing useful\n")
        write(self.ws, "openspec/changes/bad/specs/shop/x/spec.md", "# no deltas here\n")
        vs = self.rule("openspec-validate", require_tools=False)
        self.assertViolation(vs, "openspec-validate", "openspec validate --all --strict")
        self.assertEqual("openspec/", vs[0].path)


class AgentsMapTests(Base):
    def setUp(self):
        super().setUp()
        write(self.ws, "AGENTS.md", "# map\n\nRead [a](docs/agents/a.md) for a.\n")
        write(self.ws, "docs/agents/a.md", "# A\n\nSee [b](b.md#part) and [site](https://example.com/x), [top](#a).\n")
        write(self.ws, "docs/agents/b.md", "# B\n\n## Part\n")
        write(self.ws, "AGENTS.md", "# map\n\n[a](docs/agents/a.md) [b](docs/agents/b.md)\n")

    def test_clean(self):
        self.assertClean(self.rule("agents-map"))

    def test_missing_agents_md(self):
        (self.ws / "AGENTS.md").unlink()
        self.assertViolation(self.rule("agents-map"), "agents-map", "missing")

    def test_over_limit(self):
        write(self.ws, "AGENTS.md", "[a](docs/agents/a.md) [b](docs/agents/b.md)\n" + "x" * 6000)
        self.assertViolation(self.rule("agents-map"), "agents-map", "over the 6000 limit")

    def test_at_limit_is_fine(self):
        head = "[a](docs/agents/a.md) [b](docs/agents/b.md)\n"
        write(self.ws, "AGENTS.md", head + "x" * (6000 - len(head)))
        self.assertEqual(6000, (self.ws / "AGENTS.md").stat().st_size)
        self.assertClean(self.rule("agents-map"))

    def test_doc_not_linked(self):
        write(self.ws, "docs/agents/c.md", "# C\n")
        vs = self.rule("agents-map")
        self.assertViolation(vs, "agents-map", "is not linked from AGENTS.md")
        self.assertEqual("docs/agents/c.md", vs[0].path)

    def test_broken_link_in_agents_md(self):
        write(self.ws, "AGENTS.md", "[a](docs/agents/a.md) [b](docs/agents/b.md) [x](docs/agents/gone.md)\n")
        self.assertViolation(self.rule("agents-map"), "agents-map", "link to docs/agents/gone.md does not resolve")

    def test_broken_link_in_doc_is_relative_to_the_doc(self):
        write(self.ws, "docs/agents/a.md", "[up](../../GLOSSARY-MAP.md)\n")
        self.assertViolation(self.rule("agents-map"), "agents-map", "GLOSSARY-MAP.md does not resolve")
        write(self.ws, "GLOSSARY-MAP.md", "# map\n")
        self.assertClean(self.rule("agents-map"))

    def test_urls_anchors_and_code_are_ignored(self):
        write(self.ws, "docs/agents/a.md",
              "[u](https://x.test/p) [m](mailto:a@b.c) [h](#here) `[c](nope.md)`\n\n```\n[f](nope2.md)\n```\n")
        self.assertClean(self.rule("agents-map"))


class AgentsMapLinkTests(Base):
    """Which links the agents-map rule sees, and which anchors it accepts."""

    def setUp(self):
        super().setUp()
        write(self.ws, "docs/agents/a.md", "# A\n")
        write(self.ws, "docs/agents/b.md", "# B\n\n## Products and Linear projects\n\n## Part\n\n## Part\n\n## Under_score-dash\n")
        write(self.ws, "docs/agents/a b.md", "# Spaced\n")
        write(self.ws, "docs/agents/c(1).md", "# Paren\n")

    def agents(self, extra):
        write(self.ws, "AGENTS.md", "[a](docs/agents/a.md) [b](docs/agents/b.md) [s](<docs/agents/a b.md>) "
                                      "[p](docs/agents/c%281%29.md)\n" + extra)

    def test_clean_variants(self):
        self.agents("[x](<docs/agents/a b.md>) [y](docs/agents/a%20b.md) [z](docs/agents/c(1).md)\n")
        self.assertClean(self.rule("agents-map"))

    def test_broken_angle_percent_and_paren_targets(self):
        self.agents("[x](<docs/agents/nope one.md>) [y](docs/agents/nope%20two.md) [z](docs/agents/nope(3).md)\n")
        msgs = [v.message for v in self.rule("agents-map")]
        self.assertEqual(3, len(msgs), msgs)

    def test_reference_style_link_is_reported_once(self):
        self.agents("[a][r]\n\n[r]: docs/agents/missing.md\n")
        msgs = [v.message for v in self.rule("agents-map") if "missing.md" in v.message]
        self.assertEqual(1, len(msgs), msgs)

    def test_reference_style_links(self):
        self.agents("[t][r] and [s][] and [r2]\n\n[r]: docs/agents/gone.md\n[s]: <docs/agents/gone2.md>\n[r2]: docs/agents/gone3.md \"T\"\n")
        msgs = " ".join(v.message for v in self.rule("agents-map"))
        for name in ("gone.md", "gone2.md", "gone3.md"):
            self.assertIn(name, msgs)

    def test_reference_style_link_counts_as_linking_a_doc(self):
        write(self.ws, "docs/agents/d.md", "# D\n")
        self.agents("[d][dd]\n\n[dd]: docs/agents/d.md\n")
        self.assertClean(self.rule("agents-map"))

    def test_unused_definition_and_brackets_are_not_links(self):
        self.agents("[ref]: docs/agents/gone.md\n\nSee [not a link] and [x][missing].\n")
        self.assertClean(self.rule("agents-map"))

    def test_code_spans_of_any_backtick_count_comments_and_indented_code_ignored(self):
        self.agents("``[a](gone1.md) ` [b](gone2.md)``\n\n<!-- [c](gone3.md)\n [d](gone4.md) -->\n\n"
                    "    [e](gone5.md)\n\n\t[f](gone6.md)\n\n~~~\n[g](gone7.md)\n~~~\n")
        self.assertClean(self.rule("agents-map"))

    def test_indented_text_inside_a_list_item_is_not_code(self):
        self.agents("- item\n\n    [h](gone8.md)\n")
        self.assertViolation(self.rule("agents-map"), "agents-map", "gone8.md does not resolve")

    def test_anchor_must_name_a_heading(self):
        self.agents("[ok](docs/agents/b.md#products-and-linear-projects) [ok2](docs/agents/b.md#part-1) "
                    "[ok3](docs/agents/b.md#under_score-dash) [bad](docs/agents/b.md#nope)\n")
        vs = self.rule("agents-map")
        self.assertEqual(1, len(vs), vs)
        self.assertIn("docs/agents/b.md#nope", vs[0].message)
        self.assertIn("heading", vs[0].message)

    def test_anchor_ignores_headings_in_code_fences_and_non_markdown(self):
        write(self.ws, "docs/agents/b.md", "# B\n\n```bash\n# not a heading\n```\n")
        write(self.ws, "docs/agents/data.json", "{}\n")
        self.agents("[f](docs/agents/b.md#not-a-heading) [j](docs/agents/data.json#whatever)\n")
        vs = self.rule("agents-map")
        self.assertEqual(1, len(vs), vs)
        self.assertIn("b.md#not-a-heading", vs[0].message)


def headings_of(text):
    """Heading texts of a Markdown text; a `#` line inside a code fence is not a heading."""
    headings, fence = [], None
    for line in text.splitlines():
        m = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence is None and m:
            fence = m.group(1)
        elif fence is not None and re.match(r"^ {0,3}" + re.escape(fence[0]) + "{%d,}\\s*$" % len(fence), line):
            fence = None
        elif fence is None and re.match(r"^#+\s", line):
            headings.append(re.sub(r"^#+\s+", "", line).strip())
    return headings


class ConventionTextTests(unittest.TestCase):
    """Every rule's `convention` names a file of this repository and, when it names a section, a heading."""

    def test_fenced_lines_are_not_headings(self):
        self.assertEqual(["A", "B"], headings_of("# A\n\n```bash\n# comment\n```\n\n~~~\n# x\n~~~\n## B\n"))

    def test_conventions_point_to_existing_files_and_headings(self):
        for r in check.RULES:
            match = re.search(r"[\w./-]+\.(?:md|yaml|json|py|sh)\b", r.convention)
            self.assertIsNotNone(match, "%s: no file named in %r" % (r.id, r.convention))
            path = REPO / match.group(0)
            self.assertTrue(path.is_file(), "%s: %s does not exist" % (r.id, match.group(0)))
            section = re.search(r'section "(.+?)"(?:\s|$)', r.convention)
            if section:
                headings = headings_of(path.read_text(encoding="utf-8"))
                self.assertIn(section.group(1), headings,
                              "%s: %s has no heading %r" % (r.id, match.group(0), section.group(1)))


class CliTests(Base):
    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = check.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_clean_run(self):
        code, out, _ = self.run_main("--root", str(self.ws), "--only", "manifest,mcp-parity")
        self.assertEqual(0, code)
        self.assertEqual("check: ok (2 rules)\n", out)

    def test_violation_prints_convention_and_summary(self):
        write(self.ws, "repos.json", json.dumps({"org": "a", "repos": [{"name": "w", "url": "u", "product": ["x"]}]}))
        code, out, _ = self.run_main("--root", str(self.ws), "--only", "manifest")
        lines = out.splitlines()
        self.assertEqual(1, code)
        self.assertTrue(lines[0].startswith('manifest: repos.json: repos[0] "w": unknown key "product"'))
        self.assertEqual('  Convention: README.md, section "Manifest (`repos.json`)"', lines[1])
        self.assertEqual("check: 1 violation in 1 rule", lines[-1])

    def test_unknown_rule_is_a_usage_error(self):
        code, _, err = self.run_main("--root", str(self.ws), "--only", "nope")
        self.assertEqual(2, code)
        self.assertIn("unknown rule id(s): nope", err)

    def test_list(self):
        code, out, _ = self.run_main("--list")
        self.assertEqual(0, code)
        self.assertEqual([r.id for r in check.RULES], [l.split()[0] for l in out.splitlines()])
        self.assertEqual(9, len(check.RULES))

    def test_skip_is_reported_and_counted(self):
        with mock.patch.object(check.shutil, "which", return_value=None):
            code, out, _ = self.run_main("--root", str(self.ws), "--only", "openspec-validate")
            self.assertEqual(0, code)
            self.assertIn("openspec-validate: skipped (", out)
            self.assertTrue(out.endswith("check: ok (1 rules, 1 skipped)\n"))
            code, out, _ = self.run_main("--root", str(self.ws), "--only", "openspec-validate", "--require-tools")
        self.assertEqual(1, code)
        self.assertIn("Convention: docs/agents/openspec.md", out)

    def test_openspec_version_flag(self):
        code, out, _ = self.run_main("--root", str(REPO), "--openspec-version")
        self.assertEqual((0, check.pinned_openspec_version(REPO)[0] + "\n"), (code, out))
        code, out, err = self.run_main("--root", str(self.ws), "--openspec-version")
        self.assertEqual((2, ""), (code, out))
        self.assertIn("cannot determine", err)

    def test_openspec_ok_flag(self):
        with mock.patch.object(check, "installed_openspec_version", return_value="99.0.0"):
            code, out, err = self.run_main("--root", str(REPO), "--openspec-ok")
        self.assertEqual((1, ""), (code, out))
        self.assertIn("found 99.0.0", err)
        pin = check.pinned_openspec_version(REPO)[0]
        with mock.patch.object(check, "installed_openspec_version", return_value=pin):
            self.assertEqual(0, self.run_main("--root", str(REPO), "--openspec-ok")[0])


if __name__ == "__main__":
    unittest.main()
