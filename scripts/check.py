#!/usr/bin/env python3
"""Deterministic checks for the conventions of this meta workspace.

Each rule reports only real violations, says what to do about each one and names where its
convention is written. Run `scripts/check.py --list` for the rules, or `make check`.
Standard library only; no clone of the repos under repos/ is needed.
"""
import argparse
import collections
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import urllib.parse
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:  # the line parser below covers older Pythons
    tomllib = None

DEFAULT_ROOT = Path(__file__).resolve().parent.parent
SLUG_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SAFE_ENV_SUFFIXES = (".example", ".sample", ".template", ".dist")


def is_env_secret_name(base):
    """True for `.env` and `.env.*` file names, except templates; shared with scripts/guard.py.

    Case-insensitive: macOS file systems are, so `.ENV` is the same file as `.env`."""
    base = base.lower()
    return (base == ".env" or base.startswith(".env.")) and not base.endswith(SAFE_ENV_SUFFIXES)


class Violation(collections.namedtuple("Violation", "rule path line message")):
    def render(self):
        where = self.path if not self.line else "%s:%d" % (self.path, self.line)
        return "%s: %s: %s" % (self.rule, where, self.message)


class Skip(Exception):
    """A rule cannot run here (missing tool or not a git work tree); not a violation."""


Rule = collections.namedtuple("Rule", "id summary convention func tools")
RULES = []


def rule(rule_id, summary, convention, tools=False):
    def register(func):
        RULES.append(Rule(rule_id, summary, convention, func, tools))
        return func
    return register


def read_text(path):
    try:
        return Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def load_json(path):
    """Return (data, error message); both None when the file does not exist."""
    if not Path(path).exists():
        return None, None
    text = read_text(path)
    if text is None:
        return None, "cannot be read as UTF-8 text"
    try:
        return json.loads(text), None
    except ValueError as exc:
        return None, "is not valid JSON (%s)" % exc


def manifest_repos(root):
    """Repos of repos.json, leniently: the manifest rule reports whatever is malformed."""
    data, _ = load_json(Path(root) / "repos.json")
    repos = data.get("repos") if isinstance(data, dict) else None
    return [r for r in repos if isinstance(r, dict)] if isinstance(repos, list) else []


def known_products(root):
    found = set()
    for repo in manifest_repos(root):
        products = repo.get("products")
        if isinstance(products, list):
            found.update(p for p in products if isinstance(p, str))
    return found


def normalize_rel(value):
    """POSIX-normalized relative path (no leading `./`, no trailing `/`), or None when `value` is not a
    string, is absolute, normalizes to `.` or escapes upward with `..`. Shared with scripts/guard.py."""
    if not isinstance(value, str) or not value.strip():
        return None
    if value.startswith("/"):
        return None
    norm = posixpath.normpath(value)
    if norm == "." or norm == ".." or norm.startswith("../"):
        return None
    return norm


def manifest_root_dir(root):
    data, _ = load_json(Path(root) / "repos.json")
    value = data.get("root") if isinstance(data, dict) else None
    return normalize_rel(value) or "repos"


def nonempty_str(value):
    return isinstance(value, str) and value.strip() != ""


# ---------------------------------------------------------------------------------------------
# 1. manifest
# ---------------------------------------------------------------------------------------------

@rule("manifest", "repos.json has a known shape, valid products and unique names and paths",
      'docs/reference/workspace.md, section "Manifest (`repos.json`)"')
def check_manifest(root):
    out = []
    rel = "repos.json"

    def bad(msg):
        out.append(Violation("manifest", rel, None, msg))

    data, err = load_json(Path(root) / rel)
    if err:
        bad("file %s. Fix the syntax." % err)
        return out
    if data is None:
        bad("file not found. Create it from the example in docs/reference/workspace.md, section \"Manifest (repos.json)\".")
        return out
    if not isinstance(data, dict):
        bad("top level must be an object with the keys org, root and repos.")
        return out
    for key in sorted(data):
        if key not in ("org", "root", "repos"):
            bad('unknown top-level key "%s". Allowed keys: org, root, repos.' % key)
    if not nonempty_str(data.get("org")):
        bad('"org" must be a non-empty string (your GitHub organization).')
    if "root" in data:
        value = data["root"]
        if normalize_rel(value) is None:
            bad('"root" must be a non-empty relative path without "..", or be omitted (default "repos").')
    repos = data.get("repos")
    if not isinstance(repos, list):
        bad('"repos" must be a list of repo objects.')
        return out

    allowed = ("name", "url", "branch", "description", "path", "products", "check")
    names = collections.defaultdict(list)
    paths = collections.defaultdict(list)
    for i, repo in enumerate(repos):
        label = "repos[%d]" % i
        if not isinstance(repo, dict):
            bad("%s: must be an object with name, url and optional branch, description, path, products, check." % label)
            continue
        if nonempty_str(repo.get("name")):
            label += ' "%s"' % repo["name"]
        for key in sorted(repo):
            if key in allowed:
                continue
            if key == "product":
                hint = (' Use "products" (a list of product slugs). A misspelled key is ignored and turns a product repo '
                        "into one shared by every product.")
            else:
                hint = " Allowed keys: %s." % ", ".join(allowed)
            bad('%s: unknown key "%s".%s' % (label, key, hint))
        for key in ("name", "url"):
            if not nonempty_str(repo.get(key)):
                bad('%s: "%s" must be a non-empty string.' % (label, key))
        for key in ("branch", "path"):
            if key in repo and not nonempty_str(repo[key]):
                bad('%s: "%s" must be a non-empty string when present. Remove it to use the default.' % (label, key))
        if "description" in repo and not isinstance(repo["description"], str):
            bad('%s: "description" must be a string.' % label)
        if "check" in repo and (not nonempty_str(repo["check"])
                                or any(ord(c) < 32 or ord(c) == 127 for c in repo["check"])):
            bad('%s: "check" must be a non-empty single-line string without control characters (tabs included): the command that verifies a change in this repo, '
                'e.g. "pnpm test". Remove it when the repo has none.' % label)
        if "products" in repo:
            products = repo["products"]
            if not isinstance(products, list):
                bad('%s: "products" must be a list of product slugs.' % label)
            elif not products:
                bad('%s: "products" is empty. Omit "products" for a repo shared by every product.' % label)
            else:
                for slug in products:
                    if not isinstance(slug, str) or not SLUG_RE.match(slug):
                        bad('%s: product %s is not a slug. Use lowercase letters, digits and single hyphens, e.g. "my-product".'
                            % (label, json.dumps(slug)))
        if nonempty_str(repo.get("name")):
            names[repo["name"]].append(i)
            effective = repo["path"] if nonempty_str(repo.get("path")) else repo["name"]
            normalized = normalize_rel(effective)
            if normalized is None:
                bad('%s: path %s must be a relative path inside the clones directory: not absolute, not ".", without "..". '
                    'Fix "path" (or "name", which is the default path).' % (label, json.dumps(effective)))
            elif "/" in normalized:
                bad('%s: path %s contains "/": clones live directly under the repos directory. Use a single directory name '
                    'in "path" (or "name", which is the default path).' % (label, json.dumps(effective)))
            else:
                paths[normalized].append(i)
    for name, idx in sorted(names.items()):
        if len(idx) > 1:
            bad('name "%s" is used by repos[%s]. Names must be unique.' % (name, ", ".join(map(str, idx))))
    for path, idx in sorted(paths.items()):
        if len(idx) > 1 and len(set(repos[i]["name"] for i in idx)) > 1:
            bad('path "%s" is used by repos[%s]. Give one of them a distinct "path".'
                % (path, ", ".join(map(str, idx))))
    return out


# ---------------------------------------------------------------------------------------------
# 2. change-product
# ---------------------------------------------------------------------------------------------

def parse_simple_yaml(text):
    """Top-level `key: value` scalars, plus one level of 2-space-indented `key: value` under a
    `key:` line. This covers what .openspec.yaml uses (x-product, x-linear-project, ...) and nothing
    else: lists, anchors and multi-line scalars are not understood."""
    result = {}
    current = None
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = re.match(r"""^( *)(?:([A-Za-z0-9_-]+)|"([A-Za-z0-9_-]+)"|'([A-Za-z0-9_-]+)'):[ \t]*(.*)$""", raw)
        if not m:
            continue
        indent, value = len(m.group(1)), m.group(5).strip()
        key = m.group(2) or m.group(3) or m.group(4)
        if value[:1] in ("'", '"'):
            end = value.find(value[0], 1)
            value = value[1:end] if end > 0 else value[1:]
        else:
            value = re.sub(r"\s+#.*$", "", value).strip()
        if indent == 0:
            if value == "":
                result[key] = {}
                current = key
            else:
                result[key] = value
                current = None
        elif indent == 2 and current is not None:
            result[current][key] = value
    return result


def list_change_dirs(root):
    base = Path(root) / "openspec" / "changes"
    active, archived = [], []
    if base.is_dir():
        active = sorted(p for p in base.iterdir()
                        if p.is_dir() and p.name != "archive" and not p.name.startswith("."))
        arch = base / "archive"
        if arch.is_dir():
            archived = sorted(p for p in arch.iterdir() if p.is_dir() and not p.name.startswith("."))
    return active, archived


def relpath(root, path):
    return Path(os.path.relpath(str(path), str(root))).as_posix()


@rule("change-product", "a change has a known product exactly when repos.json declares products; spec paths agree; no tracker container is shared",
      'docs/agents/openspec.md, section "Products and trackers"')
def check_change_product(root):
    out = []
    root = Path(root)
    known = known_products(root)
    spec_shape = "<product>/<capability>/spec.md" if known else "<capability>/spec.md"
    active, archived = list_change_dirs(root)
    containers = collections.OrderedDict()

    def record_container(change_dir, meta):
        """The tracker container of a change: its Linear project or its GitHub parent issue."""
        linear, github = meta.get("x-linear-project"), meta.get("x-github-issue")
        if isinstance(linear, dict) and linear.get("id"):
            containers.setdefault("x-linear-project.id %s" % linear["id"], []).append(change_dir)
        if isinstance(github, dict) and github.get("repo") and github.get("number"):
            containers.setdefault("x-github-issue %s#%s" % (github["repo"], github["number"]), []).append(change_dir)

    for change in active:
        yaml_rel = relpath(root, change / ".openspec.yaml")
        text = read_text(change / ".openspec.yaml")
        meta = parse_simple_yaml(text) if text is not None else {}
        product = meta.get("x-product")
        product = product if isinstance(product, str) and product else None
        if text is None:
            if known:
                out.append(Violation("change-product", relpath(root, change), None,
                                     "missing .openspec.yaml. Create it with a top-level `x-product: <slug>`."))
        elif product is None:
            if known:
                out.append(Violation("change-product", yaml_rel, None,
                                     "no top-level `x-product: <slug>`. Record the one product this change belongs to."))
        elif not known:
            out.append(Violation("change-product", yaml_rel, None,
                                 '`x-product: %s` but repos.json declares no products. Remove the key, or add '
                                 '"products" to the repos in repos.json.' % product))
        elif product not in known:
            out.append(Violation("change-product", yaml_rel, None,
                                 'product "%s" is not in repos.json. Known products: %s. Fix the slug or add the product to a repo.'
                                 % (product, ", ".join(sorted(known)))))
        record_container(change, meta)
        specs = change / "specs"
        if specs.is_dir():
            for spec in sorted(specs.rglob("spec.md")):
                parts = spec.relative_to(specs).parts
                if len(parts) != (3 if known else 2):
                    out.append(Violation("change-product", relpath(root, spec), None,
                                         "delta spec must sit at specs/%s." % spec_shape
                                         + (' Move it under specs/%s/.' % product if known and product else "")))
                elif known and product and parts[0] != product:
                    out.append(Violation("change-product", relpath(root, spec), None,
                                         'delta spec is under product "%s" but the change is product "%s". '
                                         'Move it to specs/%s/%s/spec.md, or split the work into a separate change.'
                                         % (parts[0], product, product, parts[1])))

    for change in archived:
        text = read_text(change / ".openspec.yaml")
        if text is not None:
            record_container(change, parse_simple_yaml(text))

    main_specs = root / "openspec" / "specs"
    if main_specs.is_dir():
        for spec in sorted(main_specs.rglob("spec.md")):
            parts = spec.relative_to(main_specs).parts
            if len(parts) != (3 if known else 2):
                out.append(Violation("change-product", relpath(root, spec), None,
                                     "main spec must sit at openspec/specs/%s." % spec_shape))
            elif known and parts[0] not in known:
                out.append(Violation("change-product", relpath(root, spec), None,
                                     'main spec directory "%s" is not a product in repos.json. Known products: %s.'
                                     % (parts[0], ", ".join(sorted(known)))))

    for container, dirs in containers.items():
        if len(dirs) > 1:
            names = ", ".join(relpath(root, d) for d in dirs)
            out.append(Violation("change-product", relpath(root, dirs[0] / ".openspec.yaml"), None,
                                 "%s is used by %d changes: %s. Each change has its own Linear project or GitHub parent issue."
                                 % (container, len(dirs), names)))
    return out


# ---------------------------------------------------------------------------------------------
# 3. tracker
# ---------------------------------------------------------------------------------------------

TRACKERS = ("linear", "github", "none")
TRACKER_RE = re.compile(r"^x-tracker:[ \t]*(.*?)[ \t]*(?:#.*)?$", re.M)


@rule("tracker", "openspec/config.yaml sets x-tracker to linear, github or none",
      "docs/agents/issue-tracker.md")
def check_tracker(root):
    rel = "openspec/config.yaml"
    text = read_text(Path(root) / rel)
    if text is None:
        return []
    found = TRACKER_RE.search(text)
    if not found:
        return [Violation("tracker", rel, None,
                          "no top-level `x-tracker:`. Add `x-tracker: none` (or linear, github) under `schema:`.")]
    value = found.group(1).strip("'\"")
    if value not in TRACKERS:
        line = text[:found.start()].count("\n") + 1
        return [Violation("tracker", rel, line,
                          '`x-tracker: %s` is not a tracker. Use one of: %s.' % (value, ", ".join(TRACKERS)))]
    return []


# ---------------------------------------------------------------------------------------------
# 4. mcp-parity
# ---------------------------------------------------------------------------------------------

MCP_FILES = (".mcp.json", ".codex/config.toml", "opencode.json")


def split_toml_key(header):
    parts, buf, quote = [], "", None
    for ch in header:
        if quote:
            if ch == quote:
                quote = None
            else:
                buf += ch
        elif ch in ("'", '"'):
            quote = ch
        elif ch == ".":
            parts.append(buf.strip())
            buf = ""
        else:
            buf += ch
    parts.append(buf.strip())
    return parts


class UnsupportedToml(Exception):
    """The fallback TOML parser meets a construct it does not implement: only Python 3.11+ can parse this file."""


class _Escaped(str):
    """A basic string that contains a backslash: the fallback parser keeps its raw text and cannot decode it."""


BARE_KEY = r"[A-Za-z0-9_-]+"
_KEY_PART = r"""(?:%s|"[^"]*"|'[^']*')""" % BARE_KEY
KEY_PATH = r"(%s(?:\s*\.\s*%s)*)" % (_KEY_PART, _KEY_PART)
KEY_RE = re.compile(r"^\s*" + KEY_PATH + r"\s*=\s*(.*)$")
INLINE_KEY_RE = re.compile(r"\s*" + KEY_PATH + r"\s*=")
HEADER_RE = re.compile(r"^\s*\[([^\[\]]+)\]\s*(#.*)?$")


def _toml_scalar(text, i):
    """(string or None, index after it) for the single-line value at text[i]: strings are returned, the
    rest is skipped up to a top-level comma or closing brace."""
    if text[i:i + 1] in ('"', "'"):
        quote, j = text[i], i + 1
        while j < len(text) and text[j] != quote:
            j += 2 if quote == '"' and text[j] == "\\" else 1
        raw = text[i + 1:j]
        return (_Escaped(raw) if quote == '"' and "\\" in raw else raw), j + 1
    depth, j = 0, i
    while j < len(text):
        ch = text[j]
        if ch in "\"'":
            j = _toml_scalar(text, j)[1]
            continue
        if ch in "[{":
            depth += 1
        elif ch in "]}" and depth == 0:
            break
        elif ch in "]}":
            depth -= 1
        elif ch == "," and depth == 0:
            break
        elif ch == "#" and depth == 0:
            break
        j += 1
    return None, j


def _toml_value(text, i):
    """(value, next index): an inline table becomes a dict, a string a str, anything else None."""
    while text[i:i + 1] in (" ", "\t"):
        i += 1
    if text[i:i + 1] != "{":
        return _toml_scalar(text, i)
    table, i = {}, i + 1
    while i < len(text):
        while text[i:i + 1] in (" ", "\t", ","):
            i += 1
        if text[i:i + 1] in ("}", ""):
            return table, i + 1
        m = INLINE_KEY_RE.match(text, i)
        if not m:
            return table, len(text)
        value, i = _toml_value(text, m.end())
        _toml_assign(table, split_toml_key(m.group(1)), value)
    return table, i


def _toml_table(data, parts):
    for part in parts:
        child = data.get(part)
        if not isinstance(child, dict):
            child = data[part] = {}
        data = child


def _toml_assign(data, parts, value):
    node = data
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = node[part] = {}
        node = child
    if isinstance(value, dict) and isinstance(node.get(parts[-1]), dict):
        node[parts[-1]].update(value)
    else:
        node[parts[-1]] = value


def _servers_of(data):
    section = data.get("mcp_servers") if isinstance(data, dict) else None
    if not isinstance(section, dict):
        return {}
    for cfg in section.values():
        if isinstance(cfg, dict) and isinstance(cfg.get("url"), _Escaped):
            raise UnsupportedToml("escape sequences in a url")
    return {name: (cfg.get("url") if isinstance(cfg, dict) and isinstance(cfg.get("url"), str) else None)
            for name, cfg in section.items()}


def strip_toml_comments(text):
    """`text` without comments: a `#` outside a string, up to the end of its line."""
    lines = []
    for line in text.splitlines():
        quote, i = None, 0
        while i < len(line):
            ch = line[i]
            if quote:
                if ch == "\\" and quote == '"':
                    i += 1
                elif ch == quote:
                    quote = None
            elif ch in "\"'":
                quote = ch
            elif ch == "#":
                line = line[:i]
                break
            i += 1
        lines.append(line)
    return "\n".join(lines)


def parse_codex_servers_lines(text):
    """{server: url or None} read line by line, for Pythons without tomllib. Understands `[a.b]` tables,
    dotted keys, inline tables and bare or quoted names; it does not detect invalid TOML. It does not guess
    at what it does not implement: triple-quoted strings, `[[mcp_servers...]]` headers and escapes in a url or in
    a name raise UnsupportedToml."""
    uncommented = strip_toml_comments(text)   # a comment may say anything, `'''` included
    if '"""' in uncommented or "'''" in uncommented:
        raise UnsupportedToml("triple-quoted strings")
    data = {}
    prefix = []
    for line in text.splitlines():
        array = re.match(r"^\s*\[\[(.*?)\]\]", line)
        if array and split_toml_key(array.group(1))[0] == "mcp_servers":
            raise UnsupportedToml("array-of-tables headers")
        m = HEADER_RE.match(line)
        if m:
            if "\\" in m.group(1):
                raise UnsupportedToml("escapes in a name")
            prefix = split_toml_key(m.group(1))
            _toml_table(data, prefix)
            continue
        if re.match(r"^\s*\[", line):
            prefix = None  # not a table header we understand: its keys are not servers
            continue
        m = KEY_RE.match(line)
        if m and prefix is not None:
            if "\\" in m.group(1):
                raise UnsupportedToml("escapes in a name")
            value, _ = _toml_value(m.group(2), 0)
            _toml_assign(data, prefix + split_toml_key(m.group(1)), value)
    return _servers_of(data)


def parse_codex_servers_tomllib(text):
    """Same result through tomllib; raises ValueError for text that is not valid TOML."""
    return _servers_of(tomllib.loads(text))


def parse_codex_servers(text):
    return parse_codex_servers_tomllib(text) if tomllib is not None else parse_codex_servers_lines(text)


def mcp_servers(root):
    """{file: {server: url or None}} for every existing file; plus {file: error}."""
    declared, errors = {}, {}
    for rel in MCP_FILES:
        path = Path(root) / rel
        if rel.endswith(".toml"):
            text = read_text(path)
            if text is not None:
                try:
                    declared[rel] = parse_codex_servers(text)
                except ValueError as exc:
                    errors[rel] = "is not valid TOML (%s)" % exc
            continue
        data, err = load_json(path)
        if err:
            errors[rel] = err
        key = "mcpServers" if rel == ".mcp.json" else "mcp"
        section = data.get(key) if isinstance(data, dict) else None
        if isinstance(section, dict):
            declared[rel] = {n: (c.get("url") if isinstance(c, dict) and isinstance(c.get("url"), str) else None)
                             for n, c in section.items()}
        elif path.exists():
            declared[rel] = {}
    return declared, errors


@rule("mcp-parity", "every MCP server is declared, with the same url, in .mcp.json, .codex/config.toml and opencode.json",
      'docs/reference/workspace.md, section "MCP servers"', tools=True)
def check_mcp_parity(root, require_tools=False):
    out = []
    try:
        declared, errors = mcp_servers(root)
    except UnsupportedToml as exc:
        return tool_missing("mcp-parity", require_tools,
                            ".codex/config.toml uses TOML this Python cannot read without guessing (%s): "
                            "it needs Python 3.11+ to be parsed" % exc, ".codex/config.toml")
    for rel, err in sorted(errors.items()):
        out.append(Violation("mcp-parity", rel, None, "file %s. Fix the syntax." % err))
    names = sorted(set(n for servers in declared.values() for n in servers))
    for name in names:
        have = [f for f in MCP_FILES if name in declared.get(f, {})]
        for rel in MCP_FILES:
            if rel in errors or name in declared.get(rel, {}):
                continue
            out.append(Violation("mcp-parity", rel, None,
                                 'server "%s" is declared in %s but not in %s. Edit %s to add it, or remove it from the others.'
                                 % (name, ", ".join(have), rel, rel)))
        urls = [(f, declared[f][name]) for f in have if declared[f][name]]
        if len(set(u for _, u in urls)) > 1:
            out.append(Violation("mcp-parity", urls[0][0], None,
                                 'server "%s" has different urls: %s. Use the same url in every file.'
                                 % (name, "; ".join("%s has %s" % fu for fu in urls))))
    return out


# ---------------------------------------------------------------------------------------------
# 5. skill-exposure
# ---------------------------------------------------------------------------------------------

def frontmatter(text):
    lines = (text or "").lstrip("﻿").splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for end in range(1, len(lines)):
        if lines[end].strip() == "---":
            return lines[1:end]
    return None


def frontmatter_value(lines, key):
    """Value of a top-level key; block scalars (`>`, `|`) yield their first non-blank line."""
    for i, line in enumerate(lines):
        m = re.match(r"^%s:[ \t]*(.*)$" % re.escape(key), line)
        if not m:
            continue
        value = m.group(1).strip()
        quoted = re.match(r"""^(["'])(.*?)\1\s*(#.*)?$""", value)
        if quoted:
            return quoted.group(2)
        if value[:1] not in ("'", '"'):
            value = re.sub(r"(^|\s+)#.*$", "", value).strip()
        if re.match(r"^[>|][+-]?$", value):
            for nxt in lines[i + 1:]:
                if nxt.strip():
                    return nxt.strip() if nxt.startswith((" ", "\t")) else ""
            return ""
        return value
    return None


def skill_entries(base):
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if not p.name.startswith(".") and "--" not in p.name)


LN_HELP = ("Expose it with `mkdir -p .claude/skills/{n} && ln -s ../../../.agents/skills/{n}/SKILL.md .claude/skills/{n}/SKILL.md`; "
           "a skill with references/ gets a directory link instead: `ln -s ../../.agents/skills/{n} .claude/skills/{n}`.")


@rule("skill-exposure", "skills have valid frontmatter, are exposed to Claude Code, and nothing is a broken link",
      'docs/agents/workspace-changes.md, section "Custom skills"')
def check_skill_exposure(root):
    out = []
    root = Path(root)
    agents, claude = root / ".agents" / "skills", root / ".claude" / "skills"

    for skill in skill_entries(agents):
        md = skill / "SKILL.md"
        if not skill.is_dir() or not md.is_file():
            continue
        rel = relpath(root, md)
        lines = frontmatter(read_text(md))
        if lines is None:
            out.append(Violation("skill-exposure", rel, None, "no frontmatter. Start the file with `---`, `name:` and `description:`, then `---`."))
        else:
            name = frontmatter_value(lines, "name")
            if name != skill.name:
                out.append(Violation("skill-exposure", rel, None,
                                     'frontmatter name is %s but the directory is "%s". Set `name: %s`.'
                                     % (json.dumps(name) if name is not None else "missing", skill.name, skill.name)))
            if not frontmatter_value(lines, "description"):
                out.append(Violation("skill-exposure", rel, None, "frontmatter has no description. Add `description:` saying when to use the skill."))
        if not (claude / skill.name / "SKILL.md").is_file():
            out.append(Violation("skill-exposure", ".claude/skills/%s/SKILL.md" % skill.name, None,
                                 "skill .agents/skills/%s is not visible to Claude Code. %s" % (skill.name, LN_HELP.format(n=skill.name))))

    for entry in skill_entries(claude):
        if entry.is_symlink() and not entry.exists():
            continue  # reported below as a broken link
        if not (agents / entry.name / "SKILL.md").is_file():
            out.append(Violation("skill-exposure", relpath(root, entry), None,
                                 "no .agents/skills/%s/SKILL.md, the canonical location. Move the skill there and link it from .claude/skills/, "
                                 "or remove this entry." % entry.name))

    for base in (agents, claude):
        for dirpath, dirnames, filenames in os.walk(str(base)):
            if Path(dirpath) == base:
                dirnames[:] = [d for d in dirnames if "--" not in d]
                filenames[:] = [f for f in filenames if "--" not in f]
            for name in dirnames + filenames:
                full = Path(dirpath) / name
                if full.is_symlink() and not full.exists():
                    out.append(Violation("skill-exposure", relpath(root, full), None,
                                         "broken symlink to %s. Remove it or restore its target." % os.readlink(str(full))))

    data, err = load_json(root / "skills-lock.json")
    if err:
        out.append(Violation("skill-exposure", "skills-lock.json", None, "file %s. Fix the syntax." % err))
    skills = data.get("skills") if isinstance(data, dict) else None
    if isinstance(skills, dict):
        for key in sorted(skills):
            if not (agents / key / "SKILL.md").is_file():
                out.append(Violation("skill-exposure", "skills-lock.json", None,
                                     'locked skill "%s" has no .agents/skills/%s/SKILL.md. Restore the skill or remove its entry from the lock file.'
                                     % (key, key)))
    return out


# ---------------------------------------------------------------------------------------------
# 6. tracked-secrets
# ---------------------------------------------------------------------------------------------

def git_tracked(root):
    git = shutil.which("git")
    if not git:
        return None, "git is not installed"
    inside = subprocess.run([git, "-C", str(root), "rev-parse", "--is-inside-work-tree"],
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return False, "%s is not a git work tree" % root
    res = subprocess.run([git, "-C", str(root), "ls-files", "-z"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return [p for p in res.stdout.decode("utf-8", "replace").split("\0") if p], None


@rule("tracked-secrets", "no env file, secret-looking file or cloned repo is tracked by git",
      "env/README.md", tools=True)
def check_tracked_secrets(root, require_tools=False):
    tracked, problem = git_tracked(root)
    if tracked is None:
        if require_tools:
            return [Violation("tracked-secrets", ".", None, "%s, so tracked files cannot be listed. Install git." % problem)]
        raise Skip(problem)
    if tracked is False:
        raise Skip(problem)
    out = []
    repos_dir = manifest_root_dir(root)
    for path in tracked:
        parts = path.split("/")
        base = parts[-1]
        if parts[0] == "env":
            allowed = (path in ("env/README.md", "env/.gitkeep")
                       or (len(parts) == 3 and base == ".gitkeep"))
            if not allowed:
                out.append(Violation("tracked-secrets", path, None,
                                     "tracked file under env/. Run `git rm --cached %s`; it belongs untracked in env/<repo>/ "
                                     "(git-ignored), see env/README.md." % path))
                continue
        if path.startswith(repos_dir + "/"):
            out.append(Violation("tracked-secrets", path, None,
                                 "tracked file under %s/, which holds clones that are their own git repositories. "
                                 "Run `git rm -r --cached %s`; it belongs in the repo's own repository." % (repos_dir, repos_dir)))
            continue
        if is_env_secret_name(base):
            out.append(Violation("tracked-secrets", path, None,
                                 "tracked env file. Run `git rm --cached %s` and keep it untracked in env/<repo>/ (see env/README.md); "
                                 "commit a `%s.example` without values if a template is needed." % (path, base)))
    return out


# ---------------------------------------------------------------------------------------------
# 7. openspec-validate
# ---------------------------------------------------------------------------------------------

PIN_RE = re.compile(r"^\d+\.\d+\.\d+$")
PIN_FILE = "openspec/cli-version"


def pinned_openspec_version(root):
    """(version or None, error text or None) from openspec/cli-version."""
    path = Path(root) / PIN_FILE
    if not path.is_file():
        return None, "%s not found" % PIN_FILE
    text = read_text(path)
    if text is None:
        return None, "%s cannot be read as UTF-8 text" % PIN_FILE
    version = text.strip()
    if not PIN_RE.match(version):
        return None, "%s must contain one version such as 2.1.1, found %r" % (PIN_FILE, version[:40])
    return version, None


def installed_openspec_version():
    exe = shutil.which("openspec")
    if not exe:
        return None
    try:
        res = subprocess.run([exe, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             universal_newlines=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    return res.stdout.strip() or None if res.returncode == 0 else None


def version_satisfies(installed, minimum):
    """True when `installed` is `minimum` or newer within the same major version."""
    found = re.match(r"^(\d+)\.(\d+)\.(\d+)", installed or "")
    if not found:
        return False
    have, need = tuple(int(n) for n in found.groups()), tuple(int(n) for n in minimum.split("."))
    return have[0] == need[0] and have >= need


def tool_missing(rule_id, require_tools, reason, path="."):
    if require_tools:
        return [Violation(rule_id, path, None, reason)]
    raise Skip(reason)


def require_cli(rule_id, root, require_tools):
    """Violations when openspec/cli-version is invalid or the CLI is older than it or of another major
    version; raises Skip when `require_tools` is off. Returns None when the installed CLI will do."""
    pin, err = pinned_openspec_version(root)
    if pin is None:
        return [Violation(rule_id, PIN_FILE, None,
                          "invalid: %s. Write the version number alone, for example 2.1.1." % err)]
    installed = installed_openspec_version()
    if not version_satisfies(installed, pin):
        major = pin.split(".")[0]
        return tool_missing(rule_id, require_tools,
                            "openspec %s or a newer %s.x required (%s), found %s. Install it: npm i -g @fission-ai/openspec@%s"
                            % (pin, major, PIN_FILE, installed or "none", pin))
    return None


@rule("openspec-validate", "`openspec validate --all --strict` passes for every change and spec",
      "docs/agents/openspec.md", tools=True)
def check_openspec_validate(root, require_tools=False):
    root = Path(root)
    if not (root / "openspec").is_dir():
        return []
    if (root / PIN_FILE).is_file():
        problem = require_cli("openspec-validate", root, require_tools)
        if problem is not None:
            return problem
    exe = shutil.which("openspec")
    if not exe:
        return tool_missing("openspec-validate", require_tools,
                            "the openspec CLI is not installed. Install it: npm i -g @fission-ai/openspec", "openspec")
    env = dict(os.environ, DO_NOT_TRACK="1", NO_COLOR="1")
    res = subprocess.run([exe, "validate", "--all", "--strict"], cwd=str(root), env=env, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, universal_newlines=True, timeout=300)
    if res.returncode == 0:
        return []
    lines = [l.rstrip() for l in res.stdout.splitlines() if l.strip()]
    failing = [l for l in lines if re.search(r"✗|✖|\[ERROR\]|\[WARNING\]|Totals:|[Ee]rror", l)] or lines
    shown = failing[:20]
    more = " (+%d more lines)" % (len(failing) - 20) if len(failing) > 20 else ""
    return [Violation("openspec-validate", "openspec/", None,
                      "`openspec validate --all --strict` failed (exit %d). Fix what it reports, then run it again:\n    %s%s"
                      % (res.returncode, "\n    ".join(shown), more))]


# ---------------------------------------------------------------------------------------------
# 8. guardrails
# ---------------------------------------------------------------------------------------------

GUARD_SCRIPT = "scripts/guard.py"
# agent, config file, "json" when the file must parse as JSON else "text", value of `--agent`
GUARD_WIRING = (
    ("Claude Code", ".claude/settings.json", "json", "claude"),
    ("Codex", ".codex/hooks.json", "json", "codex"),
    ("OpenCode", ".opencode/plugins/guard.js", "text", "opencode"),
)
GUARD_SHELL_TOOL = "Bash"   # the name both Claude Code and Codex give their shell tool in hook matchers


def matches_tool(matcher, tool):
    """True when a hook `matcher` (a regex; empty or `*` means every tool) covers `tool`."""
    if matcher in (None, "", "*"):
        return True
    if not isinstance(matcher, str):
        return False
    try:
        return re.fullmatch(matcher, tool) is not None
    except re.error:
        return False


def has_guard_hook(data, agent_flag):
    """True when `hooks.PreToolUse` has a hook that runs scripts/guard.py with `--agent <agent_flag>` on the shell tool."""
    hooks = data.get("hooks") if isinstance(data, dict) else None
    groups = hooks.get("PreToolUse") if isinstance(hooks, dict) else None
    if not isinstance(groups, list):
        return False
    call = re.compile(r"--agent[ =]+['\"]?%s(?![\w-])" % re.escape(agent_flag))
    for group in groups:
        if not isinstance(group, dict) or not matches_tool(group.get("matcher"), GUARD_SHELL_TOOL):
            continue
        for hook in group.get("hooks") or []:
            command = hook.get("command") if isinstance(hook, dict) else None
            if isinstance(command, str) and GUARD_SCRIPT in command and call.search(command):
                return True
    return False


def strip_js_comments(text):
    """`text` without `//` and `/* */` comments; quotes and template literals are respected."""
    out, quote = [], None
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if quote:
            out.append(c)
            if c == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 1
            elif c == quote:
                quote = None
        elif c in "'\"`":
            quote = c
            out.append(c)
        elif text.startswith("//", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        elif text.startswith("/*", i):
            end = text.find("*/", i + 2)
            i = n if end < 0 else end + 2
            out.append(" ")
            continue
        else:
            out.append(c)
        i += 1
    return "".join(out)


def has_guard_plugin(text, agent_flag):
    """True when the code of an OpenCode plugin (comments aside) names the script, `--agent <flag>` and a before-execution hook."""
    code = strip_js_comments(text)
    return (GUARD_SCRIPT in code
            and re.search(r"--agent.{0,60}?%s" % re.escape(agent_flag), code, re.S) is not None
            and re.search(r"\bexecute\.before\b", code) is not None)


@rule("guardrails", "scripts/guard.py is executable and each agent's hook or plugin runs it before shell tool calls",
      'docs/reference/guardrails.md, section "Guardrails"')
def check_guardrails(root):
    root = Path(root)
    out = []
    script = root / GUARD_SCRIPT
    if not script.is_file():
        out.append(Violation("guardrails", GUARD_SCRIPT, None,
                             "missing. Restore it from the harness repository; every agent hook calls it."))
    elif not os.access(str(script), os.X_OK):
        out.append(Violation("guardrails", GUARD_SCRIPT, None, "is not executable. Run `chmod +x %s`." % GUARD_SCRIPT))
    for agent, rel, kind, flag in GUARD_WIRING:
        path = root / rel
        restore = "Restore it from the harness repository so %s runs %s before each tool call." % (agent, GUARD_SCRIPT)
        if not path.is_file():
            out.append(Violation("guardrails", rel, None, "missing. " + restore))
            continue
        if kind == "json":
            data, err = load_json(path)
            if err:
                out.append(Violation("guardrails", rel, None, "%s. Fix the file or %s" % (err, restore[0].lower() + restore[1:])))
                continue
            found = has_guard_hook(data, flag)
            how = "in a PreToolUse hook that matches %s with `--agent %s`" % (GUARD_SHELL_TOOL, flag)
        else:
            text = read_text(path)
            found = text is not None and has_guard_plugin(text, flag)
            how = "in code (comments do not count): a `tool.execute.before` hook that runs it with `--agent %s`" % flag
        if not found:
            out.append(Violation("guardrails", rel, None, "does not invoke %s %s. %s" % (GUARD_SCRIPT, how, restore)))
    return out


# ---------------------------------------------------------------------------------------------
# 9. agents-map
# ---------------------------------------------------------------------------------------------

AGENTS_MAP_LIMIT = 6000
FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
LIST_ITEM_RE = re.compile(r"^ {0,3}(?:[-*+]|[0-9]{1,9}[.)])(?:[ \t]|$)")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
CODE_SPAN_RE = re.compile(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", re.S)
REF_DEFINITION_RE = re.compile(r"^ {0,3}\[((?:[^\]\\]|\\.)+)\]:[ \t]*(?:<([^>\n]*)>|(\S+))[ \t]*(?:[\"'(].*)?$")
HEADING_RE = re.compile(r"^ {0,3}#{1,6}[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")


def code_free_lines(text):
    """The lines of `text` with fenced code, indented code and HTML comments blanked out."""
    lines = HTML_COMMENT_RE.sub(lambda m: re.sub(r"[^\n]", "", m.group(0)), text).splitlines()
    out, fence, in_list, previous_blank = [], None, False, True
    for line in lines:
        if fence is not None:
            if re.match(r"^ {0,3}" + re.escape(fence[0]) + "{%d,}[ \\t]*$" % len(fence), line):
                fence = None
            out.append("")
            continue
        opened = FENCE_OPEN_RE.match(line)
        if opened:
            fence = opened.group(1)
            out.append("")
            continue
        blank = not line.strip()
        indented = line.startswith("    ") or line.startswith("\t")
        if LIST_ITEM_RE.match(line):
            in_list = True
        elif not blank and not indented:
            in_list = False
        if indented and not in_list and previous_blank:
            out.append("")      # an indented code block follows a blank line, outside a list; it lasts while lines stay indented
            continue
        out.append(line)
        previous_blank = blank
    return out


def _balanced_destination(text, i):
    """(destination, index after it) for a link destination that starts at text[i]; None when malformed."""
    n = len(text)
    while i < n and text[i] in " \t\n":
        i += 1
    if i < n and text[i] == "<":
        end = text.find(">", i + 1)
        if end < 0 or "\n" in text[i:end]:
            return None
        return text[i + 1:end], end + 1
    depth, j = 0, i
    while j < n and not text[j].isspace():
        if text[j] == "\\":
            j += 2
            continue
        if text[j] == "(":
            depth += 1
        elif text[j] == ")":
            if depth == 0:
                break
            depth -= 1
        j += 1
    return (text[i:j], j) if j > i else None


def _normalise_label(label):
    return " ".join(label.split()).lower()


def markdown_links(text):
    """Destinations of the links of a Markdown text, fragment included; code and comments excluded.

    Inline links `[t](dest)` (also `<dest with spaces>` and balanced parentheses) and reference
    links `[t][ref]`, `[ref][]` and `[ref]` whose `[ref]: dest` definition exists."""
    lines = code_free_lines(text)
    definitions, body = {}, []
    for line in lines:
        m = REF_DEFINITION_RE.match(line)
        if m:
            definitions.setdefault(_normalise_label(m.group(1)), m.group(2) if m.group(2) is not None else m.group(3))
        else:
            body.append(line)
    body = CODE_SPAN_RE.sub(lambda m: " " * len(m.group(0)), "\n".join(body))
    found = []
    for m in re.finditer(r"\[((?:[^\[\]\\]|\\.)*)\]", body):
        end = m.end()
        if body.startswith("(", end):
            parsed = _balanced_destination(body, end + 1)
            if parsed:
                rest = body[parsed[1]:]
                if re.match(r"""\s*(?:"[^"]*"|'[^']*'|\([^)]*\))?\s*\)""", rest):
                    found.append(parsed[0])
            continue
        label = m.group(1)
        if body.startswith("[", end):
            close = body.find("]", end)
            if close > 0:
                label = body[end + 1:close] or label
        key = _normalise_label(label)
        if key in definitions:
            found.append(definitions[key])
    return found


def github_slug(heading):
    """The anchor GitHub gives a heading: lowercase, only letters, digits, spaces, hyphens and underscores, spaces to hyphens."""
    heading = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    return re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")


def markdown_anchors(text):
    """The set of heading anchors of a Markdown text; headings in code fences do not count."""
    seen, anchors = collections.Counter(), set()
    for line in code_free_lines(text):
        m = HEADING_RE.match(line)
        if m:
            slug = github_slug(m.group(1).strip())
            anchors.add(slug if not seen[slug] else "%s-%d" % (slug, seen[slug]))
            seen[slug] += 1
    return anchors


def split_link(raw):
    """(path, fragment) of a relative link destination; None for URLs, same-file anchors and empty paths."""
    path, _, fragment = raw.partition("#")
    path = urllib.parse.unquote(path)
    if not path or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", path) or path.startswith("//"):
        return None
    return path, urllib.parse.unquote(fragment)


@rule("agents-map", "AGENTS.md is a map of at most 6000 bytes, links every docs/agents/*.md, and relative links in the docs resolve",
      'docs/reference/checks.md, section "AGENTS.md is a map"')
def check_agents_map(root):
    out = []
    root = Path(root)
    agents = root / "AGENTS.md"
    if not agents.is_file():
        return [Violation("agents-map", "AGENTS.md", None,
                          "missing. Every agent loads it first: restore it as a short map of the rules that hold in every session.")]
    size = agents.stat().st_size
    if size > AGENTS_MAP_LIMIT:
        out.append(Violation("agents-map", "AGENTS.md", None,
                             "is %d bytes, over the %d limit. Move detail to a file in docs/agents/ and link it from the map."
                             % (size, AGENTS_MAP_LIMIT)))
    docs_dir = root / "docs" / "agents"
    docs = sorted(docs_dir.glob("*.md")) if docs_dir.is_dir() else []
    reference_dir = root / "docs" / "reference"
    others = [p for p in [root / "README.md"] if p.is_file()]
    others += sorted(reference_dir.glob("*.md")) if reference_dir.is_dir() else []
    linked = set()
    for md in [agents] + docs + others:
        text = read_text(md)
        if text is None:
            continue
        reported = set()
        for raw in markdown_links(text):
            link = split_link(raw)
            if link is None:
                continue
            target, fragment = link
            resolved = Path(os.path.normpath(str(md.parent / target)))
            if md == agents:
                linked.add(resolved)
            if not resolved.exists():
                if target not in reported:
                    reported.add(target)
                    out.append(Violation("agents-map", relpath(root, md), None,
                                         "link to %s does not resolve. Fix the path or remove the link." % target))
            elif fragment and resolved.is_file() and resolved.suffix.lower() == ".md":
                target_text = read_text(resolved)
                if target_text is not None and fragment.lower() not in markdown_anchors(target_text):
                    out.append(Violation("agents-map", relpath(root, md), None,
                                         "link to %s#%s: %s has no heading with that anchor. Fix the anchor "
                                         "(GitHub's slug of the heading) or the heading." % (target, fragment, target)))
    for md in docs:
        if Path(os.path.normpath(str(md))) not in linked:
            out.append(Violation("agents-map", relpath(root, md), None,
                                 "is not linked from AGENTS.md. Add a line to the map saying when to read it."))
    return out


# ---------------------------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------------------------

def run_rule(r, root, require_tools):
    """(violations, skip reason or None)."""
    try:
        return (r.func(root, require_tools) if r.tools else r.func(root)), None
    except Skip as skip:
        return [], str(skip)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check the conventions of this meta workspace.")
    parser.add_argument("--root", default=str(DEFAULT_ROOT), help="workspace to check (default: parent of scripts/)")
    parser.add_argument("--only", help="comma-separated rule ids to run")
    parser.add_argument("--list", action="store_true", help="list the rules and exit")
    parser.add_argument("--require-tools", action="store_true",
                        help="a rule that cannot run for lack of a tool is a violation, not a skip")
    parser.add_argument("--openspec-version", action="store_true",
                        help="print the OpenSpec CLI version of openspec/cli-version (the one CI installs) and exit")
    parser.add_argument("--openspec-ok", action="store_true",
                        help="exit 0 when the installed OpenSpec CLI is that version or a newer one of the same major")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2
    root = Path(args.root).resolve()

    if args.list:
        for r in RULES:
            print("%-20s %s" % (r.id, r.summary))
        return 0
    if args.openspec_version:
        version, err = pinned_openspec_version(root)
        if version is None:
            print("check: cannot determine the OpenSpec version: %s" % err, file=sys.stderr)
            return 2
        print(version)
        return 0
    if args.openspec_ok:
        version, err = pinned_openspec_version(root)
        if version is None:
            print("check: cannot determine the OpenSpec version: %s" % err, file=sys.stderr)
            return 2
        installed = installed_openspec_version()
        if version_satisfies(installed, version):
            return 0
        print("openspec %s or a newer %s.x required (%s), found %s"
              % (version, version.split(".")[0], PIN_FILE, installed or "none"), file=sys.stderr)
        return 1
    if not root.is_dir():
        print("check: --root %s is not a directory" % args.root, file=sys.stderr)
        return 2
    selected = RULES
    if args.only:
        wanted = [w.strip() for w in args.only.split(",") if w.strip()]
        unknown = [w for w in wanted if w not in [r.id for r in RULES]]
        if unknown:
            print("check: unknown rule id(s): %s. Known: %s" % (", ".join(unknown), ", ".join(r.id for r in RULES)),
                  file=sys.stderr)
            return 2
        selected = [r for r in RULES if r.id in wanted]

    failed = skipped = total = 0
    for r in selected:
        violations, skip = run_rule(r, root, args.require_tools)
        if skip is not None:
            skipped += 1
            print("%s: skipped (%s)" % (r.id, skip))
        for v in violations:
            print(v.render())
            total += 1
        if violations:
            failed += 1
            print("  Convention: %s" % r.convention)
    skip_note = " (%d skipped)" % skipped if skipped else ""
    if total:
        print("check: %d violation%s in %d rule%s%s" % (total, "" if total == 1 else "s", failed,
                                                        "" if failed == 1 else "s", skip_note))
        return 1
    print("check: ok (%d rules%s)" % (len(selected), ", %d skipped" % skipped if skipped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
