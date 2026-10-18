#!/usr/bin/env python3
"""Offline conformance tests for the portable Agent Plugins 1.0.0 packaging."""
import ast
import glob
import json
import os
import re
import sys
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from finance.mcp import smoke_test
from finance.tests.harness import check, summary

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def _load(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        return json.load(fh)

portable = _load("plugin.json")
claude = _load(".claude-plugin/plugin.json")
portable_mcp = _load("mcp.json")
claude_mcp = _load(".mcp.json")

PLUGIN_ALLOWED = {"$schema", "name", "version", "description", "author",
                  "homepage", "repository", "license", "keywords", "extensions"}
NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$")

check("plugin.json $schema is the 1.0.0 identifier",
      portable.get("$schema") == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
      portable.get("$schema"))
check("plugin.json declares a name", bool(portable.get("name")))
check("plugin.json name is 1-64 chars", 1 <= len(portable.get("name", "")) <= 64)
check("plugin.json name matches the spec pattern",
      bool(NAME_RE.match(portable.get("name", ""))), portable.get("name"))
check("plugin.json name has no consecutive -- or ..",
      "--" not in portable.get("name", "") and ".." not in portable.get("name", ""))
check("plugin.json has no keys outside the closed set",
      set(portable) <= PLUGIN_ALLOWED, str(set(portable) - PLUGIN_ALLOWED))
check("plugin.json author is an object (name/email/url only)",
      isinstance(portable.get("author"), dict)
      and set(portable["author"]) <= {"name", "email", "url"},
      str(portable.get("author")))
check("plugin.json does NOT carry Claude-only top-level keys",
      not ({"skills", "agents", "hooks", "commands", "mcpServers"} & set(portable)))

if "extensions" in portable:
    ext = portable["extensions"]
    check("extensions is an object", isinstance(ext, dict))
    check("extensions keys are reverse-domain namespaces",
          all("." in k for k in ext), str(list(ext)))
    check("extensions carries the claude-code namespace",
          "com.anthropic.claude-code" in ext, str(list(ext)))

check("portable name == Claude name", portable.get("name") == claude.get("name"))
check("portable version == Claude version", portable.get("version") == claude.get("version"))
check("portable keywords == Claude keywords",
      portable.get("keywords") == claude.get("keywords"))

skills_dir = os.path.join(ROOT, "skills")
discovered = {d for d in os.listdir(skills_dir)
              if os.path.isfile(os.path.join(skills_dir, d, "SKILL.md"))}
claude_skills = {p.rsplit("/", 1)[-1] for p in claude.get("skills", [])}
check("every Claude-listed skill has a discoverable SKILL.md",
      claude_skills <= discovered, str(claude_skills - discovered))
check("skills/ discovery is non-empty", len(discovered) > 0)

check("mcp.json $schema is the 1.0.0 identifier",
      portable_mcp.get("$schema") == "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
      portable_mcp.get("$schema"))
check("mcp.json has only $schema and mcpServers",
      set(portable_mcp) == {"$schema", "mcpServers"}, str(set(portable_mcp)))

VALID_TYPES = {"stdio", "streamable-http", "sse"}
RESERVED_ENV = {"PLUGIN_ROOT", "PLUGIN_DATA"}
servers = portable_mcp.get("mcpServers", {})

for name, entry in servers.items():
    check(f"[{name}] declares a valid transport type",
          entry.get("type") in VALID_TYPES, entry.get("type"))
    if entry.get("type") == "stdio":
        cmd = entry.get("command", "")
        check(f"[{name}] command is a bare token or ./ plugin-relative path",
              cmd.startswith("./") or ("/" not in cmd and cmd != ""), cmd)
        check(f"[{name}] command carries no ${{...}} placeholder (not expanded per spec)",
              "${" not in cmd, cmd)
        env = entry.get("env", {})
        check(f"[{name}] env does not set the reserved PLUGIN_ROOT/PLUGIN_DATA keys",
              not (RESERVED_ENV & set(env)), str(RESERVED_ENV & set(env)))
        if cmd.startswith("./"):
            target = os.path.join(ROOT, cmd[2:])
            check(f"[{name}] command target exists", os.path.isfile(target), target)
            check(f"[{name}] command target is executable", os.access(target, os.X_OK), target)

check("portable mcp.json exposes the same servers as .mcp.json",
      set(servers) == set(claude_mcp.get("mcpServers", {})),
      str(set(servers) ^ set(claude_mcp.get("mcpServers", {}))))

check("portable mcp.json carries no dead EVERYTHING_FINANCE_PLUGIN_ROOT",
      all("EVERYTHING_FINANCE_PLUGIN_ROOT" not in e.get("env", {}) for e in servers.values()))

def _declared_tools(server):
    with open(os.path.join(ROOT, "finance", "mcp", f"{server}.py"), encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    return {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
            and any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                    and d.func.attr == "tool" for d in node.decorator_list)}

check("smoke_test covers every server module", set(smoke_test.CASES) ==
      {f[:-3] for f in os.listdir(os.path.join(ROOT, "finance", "mcp"))
       if f.endswith(".py") and not f.startswith("_") and f != "smoke_test.py"},
      str(set(smoke_test.CASES)))
for server, cases in smoke_test.CASES.items():
    declared, covered = _declared_tools(server), {name for name, _, _ in cases}
    check(f"[{server}] every declared tool has a smoke case",
          declared <= covered, str(sorted(declared - covered)))
    check(f"[{server}] every smoke case names a declared tool",
          covered <= declared, str(sorted(covered - declared)))

_AGENT_NAMES = tuple(sorted(
    f[:-3] for f in os.listdir(os.path.join(ROOT, "agents")) if f.endswith(".md")))
_DISPATCH_RE = re.compile(r"`(" + "|".join(_AGENT_NAMES) + r")`")
_SKILL_FILES = sorted(glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md")))
_AGENT_FILES = sorted(glob.glob(os.path.join(ROOT, "agents", "*.md")))


def _text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


for rel in _SKILL_FILES:
    lines = _text(rel).splitlines()
    bare = [ln for ln in lines
            if (ln.startswith("|") or "fork " in ln.lower()) and _DISPATCH_RE.search(ln)]
    check(f"{os.path.basename(os.path.dirname(rel))} names every dispatched agent "
          f"`everything-finance:<agent>`", not bare, bare[0][:120] if bare else "")

# One code path: skills and agents reach the library only through tools.
_DIRECT = re.compile(r"python3? |PYTHONPATH|finance\.(compute|sources|report)\b|from finance|scripts/")
for path in _SKILL_FILES + _AGENT_FILES + [os.path.join(ROOT, "RULES.md")]:
    hits = [ln for ln in _text(path).splitlines() if _DIRECT.search(ln)]
    check(f"{os.path.relpath(path, ROOT)} reaches code only through tools", not hits,
          hits[0][:120] if hits else "")
check("no skill ships code", not glob.glob(os.path.join(ROOT, "skills", "*", "scripts")))

_mgmt = _text(os.path.join(ROOT, "skills", "management-analysis", "SKILL.md"))
check("management-analysis computes the gate arithmetic through run_governance_checks",
      "run_governance_checks" in _mgmt)
_tech = _text(os.path.join(ROOT, "skills", "technical-analysis", "SKILL.md"))
check("technical-analysis reads indicators from the indicator-of-record tool",
      "get_technicals(" in _tech)


def _agent_tools(name):
    return re.search(r"^tools: (.*)$", _text(os.path.join(ROOT, "agents", name + ".md")), re.M).group(1)


for _skill, _agent in (("management-analysis", "field-analyst"), ("valuation-analysis", "terminal-analyst"),
                       ("financial-analysis", "terminal-analyst"), ("news-scan", "field-analyst")):
    if "get_prior_run(" in _text(os.path.join(ROOT, "skills", _skill, "SKILL.md")):
        _granted = _agent_tools(_agent)
        check(f"{_agent} can reach get_prior_run, which {_skill} calls",
              "finance-workflow__get_prior_run" in _granted or "finance-workflow__*" in _granted, _granted)

_sector = _text(os.path.join(ROOT, "skills", "sector-analysis", "SKILL.md"))
check("terminal-analyst can reach the issuing-authority sites sector-analysis reads policy from",
      "WebFetch" in _sector and "WebSearch" in _agent_tools("terminal-analyst")
      and "WebFetch" in _agent_tools("terminal-analyst"))
check("sector-analysis reads the growth story before the market's read",
      _sector.find("### The growth story") < _sector.find("### The market's read") != -1)

check(".env.example template ships", os.path.isfile(os.path.join(ROOT, ".env.example")))
loader = os.path.join(ROOT, "bin", "load-env.sh")
check("bin/load-env.sh exists", os.path.isfile(loader))
check("bin/load-env.sh is executable", os.access(loader, os.X_OK))
with open(loader, encoding="utf-8") as fh:
    loader_src = fh.read()
pos = [loader_src.find(f'candidates+=("{p}")')
       for p in ('$root/.env', '$data/.env')]
check("loader searches plugin dir then data dir, in that precedence",
      all(p >= 0 for p in pos) and pos == sorted(pos), str(pos))
check("loader does not privilege a vendor home like ~/.claude",
      ".claude" not in loader_src)
# Seed behavior, permissions and shell-state preservation are exercised in test_runtime.py.

_agent_files = sorted(f"./agents/{n}" for n in os.listdir(os.path.join(ROOT, "agents"))
                      if n.endswith(".md"))
_declared_agents = sorted(claude.get("agents") or [])
check("every agents/*.md file is declared in the manifest",
      set(_agent_files) <= set(_declared_agents),
      sorted(set(_agent_files) - set(_declared_agents)))
check("every declared agent exists on disk",
      set(_declared_agents) <= set(_agent_files),
      sorted(set(_declared_agents) - set(_agent_files)))

_skill_dirs = sorted(f"./skills/{n}" for n in os.listdir(os.path.join(ROOT, "skills"))
                     if os.path.isfile(os.path.join(ROOT, "skills", n, "SKILL.md")))
_declared_skills = sorted(claude.get("skills") or [])
check("every skills/*/SKILL.md is declared in the manifest",
      set(_skill_dirs) <= set(_declared_skills),
      sorted(set(_skill_dirs) - set(_declared_skills)))
check("every declared skill exists on disk",
      set(_declared_skills) <= set(_skill_dirs),
      sorted(set(_declared_skills) - set(_skill_dirs)))

# Parse frontmatter with the runtime's YAML parser; string searches miss syntax errors.
for rel in _agent_files + [path + "/SKILL.md" for path in _skill_dirs]:
    with open(os.path.join(ROOT, rel[2:]), encoding="utf-8") as fh:
        body = fh.read()
    try:
        parts = re.split(r"(?m)^---\s*$", body, maxsplit=2)
        metadata = yaml.safe_load(parts[1]) if len(parts) == 3 and not parts[0].strip() else None
        valid = (isinstance(metadata, dict) and isinstance(metadata.get("name"), str)
                 and isinstance(metadata.get("description"), str) and bool(metadata["description"].strip()))
        detail = "metadata must declare string name and description"
    except yaml.YAMLError as exc:
        valid, detail = False, str(exc).splitlines()[0]
    check(f"{rel} frontmatter parses as YAML", valid, detail)

for rel in _agent_files:
    with open(os.path.join(ROOT, rel[2:]), encoding="utf-8") as fh:
        head = fh.read(600)
    stem = os.path.basename(rel)[:-3]
    check(f"{stem} frontmatter name matches its filename",
          f"\nname: {stem}\n" in head, head[:120])

_servers = set(claude_mcp.get("mcpServers") or {})
_PLUGIN_PREFIX = f"plugin_{claude['name']}_"
_TOOLS = {f"finance-{name}": _declared_tools(name) for name in smoke_test.CASES}


def _grants(body, key):
    line = re.search(rf"^{key}: (.*)$", body, re.M)
    return [x.strip() for x in line.group(1).split(",") if x.strip().startswith("mcp__")] if line else []


def _check_grant(owner, pat):
    server, tool = pat[len("mcp__"):].rsplit("__", 1)
    bare = server[len(_PLUGIN_PREFIX):] if server.startswith(_PLUGIN_PREFIX) else server
    check(f"{owner} grants a server the plugin declares: {pat}", bare in _servers, sorted(_servers))
    if bare in _TOOLS and tool != "*":
        check(f"{owner} grants a tool {bare} declares: {tool}", tool in _TOOLS[bare], sorted(_TOOLS[bare]))
    return bare, tool


for path in _AGENT_FILES + _SKILL_FILES:
    body = _text(path)
    owner = os.path.relpath(path, ROOT)
    pats = _grants(body, "tools" if "/agents/" in path else "allowed-tools")
    for pat in pats:
        bare, tool = _check_grant(owner, pat)
        check(f"{owner} grants {bare}__{tool} under both the qualified and bare name",
              f"mcp__{_PLUGIN_PREFIX}{bare}__{tool}" in pats and f"mcp__{bare}__{tool}" in pats, pats)

# A tool a skill calls is one its grant reaches.
_CALL = re.compile(r"`([a-z_]+)\(")
for path in _SKILL_FILES:
    body = _text(path)
    pats = _grants(body, "allowed-tools")
    reach = set()
    for pat in pats:
        server, tool = pat[len("mcp__"):].rsplit("__", 1)
        bare = server[len(_PLUGIN_PREFIX):] if server.startswith(_PLUGIN_PREFIX) else server
        reach |= _TOOLS.get(bare, set()) if tool == "*" else {tool}
    called = {name for name in _CALL.findall(body) if any(name in t for t in _TOOLS.values())}
    check(f"{os.path.basename(os.path.dirname(path))} is granted every finance tool it calls",
          called <= reach, sorted(called - reach))

_LEGS = (
    "skills/technical-analysis/SKILL.md",
    "skills/financial-analysis/SKILL.md",
    "skills/news-scan/SKILL.md",
    "skills/sector-analysis/SKILL.md",
    "skills/valuation-analysis/assets/dcf-report.example.md",
    "skills/management-analysis/assets/management-scorecard.example.md",
)
for rel in _LEGS:
    body = _text(os.path.join(ROOT, rel))
    leg = rel.split("/")[1]
    check(f"{leg} leg report defines ## Findings", "## Findings" in body, rel)
    after = body.split("## Findings", 1)[-1]
    check(f"{leg} closes ## Findings with a heading",
          any(ln.startswith("## ") for ln in after.splitlines()),
          "nothing follows ## Findings — it runs to the end of the report")

_rules = _text(os.path.join(ROOT, "RULES.md"))
check("the forked-agent protocol defines the Findings/Detail boundary",
      "## Findings" in _rules and "## Detail" in _rules)
check("the prose standard is stated once, in RULES.md", "## How a report reads" in _rules)
for path in _AGENT_FILES:
    body = _text(path)
    stem = os.path.basename(path)[:-3]
    check(f"{stem} follows the shared forked-agent protocol", "Running as a forked agent" in body)
    check(f"{stem} does not restate the prose standard",
          "Short paragraphs" not in body and "How the report reads" not in body)
check("report-writer is the one consumer that reads in full",
      "reads every paper **in full**" in _text(os.path.join(ROOT, "agents", "report-writer.md")))
_claude_md = _text(os.path.join(ROOT, "CLAUDE.md"))
check("CLAUDE.md imports the runtime rules rather than restating them",
      "@RULES.md" in _claude_md and "## How a report reads" not in _claude_md)
check("the portable manifest ships RULES.md as the instructions",
      portable["extensions"]["com.anthropic.claude-code"]["instructions"] == "RULES.md")

# Every bundled file a skill or agent names exists.
_LOCAL = re.compile(r"(?<![\w/])((?:assets|references)/[\w./-]+\.(?:md|html|yml))")
_SHARED = re.compile(r"(finance/report/fixtures/[\w.-]+\.json)")
for path in _SKILL_FILES:
    for target in _LOCAL.findall(_text(path)):
        check(f"{os.path.relpath(path, ROOT)} names an existing bundled file: {target}",
              os.path.isfile(os.path.join(os.path.dirname(path), target)))
for path in _SKILL_FILES + _AGENT_FILES + [os.path.join(ROOT, "RULES.md")]:
    for target in _SHARED.findall(_text(path)):
        check(f"{os.path.relpath(path, ROOT)} names an existing fixture: {target}",
              os.path.isfile(os.path.join(ROOT, target)))

# The method layer: every pointer resolves, no topic is orphaned, every citation is registered.
_METHODS = os.path.join(ROOT, "methods")
_topics = sorted(os.path.relpath(p, _METHODS) for p in glob.glob(os.path.join(_METHODS, "**", "*.md"), recursive=True)
                 if os.path.basename(p) != "SOURCES.md")
_pointer = re.compile(r"methods/([a-z0-9/-]+\.md)")
_referenced = set()
for path in _SKILL_FILES + _AGENT_FILES + [os.path.join(ROOT, "RULES.md")] + \
        [os.path.join(_METHODS, t) for t in _topics]:
    for target in _pointer.findall(_text(path)):
        _referenced.add(target)
        check(f"{os.path.relpath(path, ROOT)} points at an existing method: {target}",
              os.path.isfile(os.path.join(_METHODS, target)))
_ins = _text(os.path.join(ROOT, "skills", "insurance-advisor", "SKILL.md"))
for t in ("term.md", "health.md", "vehicle.md"):
    if t in _ins:
        _referenced.add("insurance/" + t)
for topic in _topics:
    check(f"method {topic} is applied by some skill or agent", topic in _referenced)
_registry = set(re.findall(r"^\| `([a-z0-9-]+)` \|", _text(os.path.join(_METHODS, "SOURCES.md")), re.M))
check("the source registry is non-empty", {"plugin", "law"} <= _registry, sorted(_registry))
for topic in _topics:
    body = _text(os.path.join(_METHODS, topic))
    check(f"method {topic} names its sources", "**Sources" in body)
    for cited in set(re.findall(r"\[([a-z][a-z0-9-]*)(?::[^\]]*)?\]", body)):
        check(f"method {topic} cites a registered source: {cited}", cited in _registry)
    for named in set(re.findall(r"`([a-z][a-z0-9-]*)`", body.split("\n\n", 2)[1] if "\n\n" in body else "")):
        if named in ("plugin", "law") or named.startswith(("varsity", "damodaran", "moneypurse", "soic")):
            check(f"method {topic} header names a registered source: {named}", named in _registry)

# The declared tool schema must accept both documented scanner request forms.
with open(os.path.join(ROOT, "finance", "mcp", "market.py")) as stream:
    market_tree = ast.parse(stream.read())
technical = next(node for node in market_tree.body if isinstance(node, ast.FunctionDef) and node.name == "run_technical_screen")
filter_arg = next(arg for arg in technical.args.args if arg.arg == "filters")
annotation = ast.unparse(filter_arg.annotation)
check("technical-screen schema accepts filter lists and basket payloads", "list" in annotation and "dict" in annotation, annotation)


# Execute the declared hook command through a shell at a path containing spaces.
# Stub scripts ensure this cannot invoke a real report hook or send a message.
import tempfile
import subprocess
from pathlib import Path
with tempfile.TemporaryDirectory(prefix="finance plugin fixture ") as directory:
    fixture = Path(directory)
    for group in _load("hooks/hooks.json")["hooks"].values():
        for entry in group:
            for hook in entry["hooks"]:
                command = hook["command"]
                name = "hook.sh"
                target = fixture / "hooks" / name
                target.parent.mkdir(exist_ok=True)
                target.write_text("#!/bin/sh\nprintf 'hook-fixture-ok'\n")
                target.chmod(0o700)
                result = subprocess.run(["/bin/sh", "-c", command], capture_output=True, text=True,
                                        env={**os.environ, "CLAUDE_PLUGIN_ROOT":str(fixture)}, timeout=10)
                check(f"{command.rsplit(' ', 1)[-1]} hook works with spaces in plugin root", result.returncode == 0 and result.stdout == "hook-fixture-ok", result.stderr)


summary()
