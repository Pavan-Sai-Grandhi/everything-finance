#!/usr/bin/env python3
"""Offline conformance tests for the portable Agent Plugins 1.0.0 packaging.

The plugin ships two manifests side by side:
  - .claude-plugin/plugin.json + .mcp.json  — Claude Code's native format (unchanged)
  - plugin.json + mcp.json                  — the portable Agent Plugins 1.0.0 format

These assertions pin the portable pair to the spec constraints AND to parity with the
Claude pair, so the two can never silently drift. No network. Spec reference:
https://agent-plugins.org/specification

Run: python3 finance/tests/test_agent_plugin.py
"""
import ast
import glob
import json
import os
import re
import sys

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

# The live smoke run is the only thing that exercises a tool against its real upstream, so
# a tool it does not call is a tool nobody ever proves works. Read the declarations with
# `ast` rather than importing the servers: the MCP SDK is supplied by the client at runtime
# and is not installed where the offline suites run.
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

# A `subagent_type` is matched literally, so an unqualified name does not resolve and the
# launch fails. The rule cannot live in prose above a table that then spells the names bare:
# the agent copies the cell. Every dispatch site — table row or Fork instruction — carries
# the qualified form.
_AGENT_NAMES = tuple(sorted(
    f[:-3] for f in os.listdir(os.path.join(ROOT, "agents")) if f.endswith(".md")))
_DISPATCH_RE = re.compile(r"`(" + "|".join(_AGENT_NAMES) + r")`")
for rel in sorted(glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md"))):
    with open(rel, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    bare = [ln for ln in lines
            if (ln.startswith("|") or "Fork " in ln) and _DISPATCH_RE.search(ln)]
    check(f"{os.path.basename(os.path.dirname(rel))} names every dispatched agent "
          f"`everything-finance:<agent>`", not bare,
          bare[0][:120] if bare else "")

# `manage_alerts` is the door to the alert inbox. A skill pointing at the module instead
# sends its agent hunting the filesystem for a file it then has to import by hand.
for rel in sorted(glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md"))):
    name = os.path.basename(os.path.dirname(rel))
    if name == "alert-manager":                 # the contract owner names its own module
        continue
    with open(rel, encoding="utf-8") as fh:
        body = fh.read()
    check(f"{name} reaches alerts through the tool, not the module",
          "finance/compute/alerts.py" not in body, rel)

with open(os.path.join(ROOT, "skills", "management-analysis", "SKILL.md"),
          encoding="utf-8") as fh:
    _mgmt = fh.read()
check("management-analysis computes the gate arithmetic through run_governance_checks",
      "run_governance_checks" in _mgmt and "python3 -m finance.compute.governance" not in _mgmt)

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
check("loader seeds $PLUGIN_DATA/.env from the template when none is found",
      'cp "$root/.env.example" "$data/.env"' in loader_src)

# --- the manifest must match the filesystem ---------------------------------- #
# A skill directory or agent file added without its manifest entry ships a plugin
# that silently does not load it.
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

# each agent file's frontmatter name matches its filename, so a dispatch by name resolves
for rel in _agent_files:
    with open(os.path.join(ROOT, rel[2:]), encoding="utf-8") as fh:
        head = fh.read(600)
    stem = os.path.basename(rel)[:-3]
    check(f"{stem} frontmatter name matches its filename",
          f"\nname: {stem}\n" in head, head[:120])

# An agent's `tools:` MCP patterns must name servers this plugin actually declares, under
# the prefix the runtime registers them with. A pattern that matches nothing does not error
# — the agent simply launches without the tool and improvises — so it is pinned here.
_servers = set(claude_mcp.get("mcpServers") or {})
_PLUGIN_PREFIX = f"plugin_{claude['name']}_"
for rel in _agent_files:
    stem = os.path.basename(rel)[:-3]
    with open(os.path.join(ROOT, rel[2:]), encoding="utf-8") as fh:
        body = fh.read()
    line = re.search(r"^tools: (.*)$", body, re.M)
    if not line:
        continue
    pats = [x.strip() for x in line.group(1).split(",") if x.strip().startswith("mcp__")]
    named = set()
    for pat in pats:
        server = pat[len("mcp__"):].rsplit("__", 1)[0]
        bare = server[len(_PLUGIN_PREFIX):] if server.startswith(_PLUGIN_PREFIX) else server
        check(f"{stem} grants a server the plugin declares: {pat}", bare in _servers, sorted(_servers))
        named.add(bare)
    # both registration spellings, or a leg silently loses the tool under one install mode
    for bare in named:
        check(f"{stem} grants {bare} under both the qualified and bare name",
              f"mcp__{_PLUGIN_PREFIX}{bare}__*" in pats and f"mcp__{bare}__*" in pats, pats)

# same rule for a skill's own allowed-tools: an unqualified name grants nothing under the
# install mode that prefixes the server, and the skill silently loses the tool
for rel in _skill_dirs:
    name = rel.split("/")[-1]
    with open(os.path.join(ROOT, rel[2:], "SKILL.md"), encoding="utf-8") as fh:
        body = fh.read()
    line = re.search(r"^allowed-tools: (.*)$", body, re.M)
    if not line:
        continue
    toks = [x.strip() for x in line.group(1).split(",") if x.strip().startswith("mcp__")]
    for tok in toks:
        server, _, rest = tok[len("mcp__"):].partition("__")
        if server.startswith(_PLUGIN_PREFIX):
            continue
        check(f"{name} grants {server}__{rest} under the qualified name too",
              f"mcp__{_PLUGIN_PREFIX}{server}__{rest}" in toks, toks)

# the Findings contract: every leg opens its report with the section AND closes it with the
# next heading, so a reader knows where the case ends. Findings with nothing after it swallows
# the whole report and the downstream instruction to build on it means nothing.
_LEGS = (
    "skills/technical-analysis/SKILL.md",
    "skills/financial-analysis/SKILL.md",
    "skills/news-scan/SKILL.md",
    "skills/sector-analysis/SKILL.md",
    "skills/valuation-analysis/assets/dcf-report.example.md",
    "skills/management-analysis/assets/management-scorecard.example.md",
)
for rel in _LEGS:
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        body = fh.read()
    leg = rel.split("/")[1]
    check(f"{leg} leg report defines ## Findings", "## Findings" in body, rel)
    after = body.split("## Findings", 1)[-1]
    closing = [ln for ln in after.splitlines() if ln.startswith("## ")]
    check(f"{leg} closes ## Findings with a heading", bool(closing),
          "nothing follows ## Findings — it runs to the end of the report")

for rel in ("agents/bull-researcher.md", "agents/bear-researcher.md",
            "agents/contest-researcher.md", "agents/portfolio-manager.md"):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as fh:
        body = fh.read()
    check(f"{os.path.basename(rel)[:-3]} builds on Findings and knows the Detail boundary",
          "## Findings" in body and "## Detail" in body, rel)

with open(os.path.join(ROOT, "agents/report-writer.md"), encoding="utf-8") as fh:
    _rw = fh.read()
check("report-writer is the one consumer that reads in full",
      "reads every paper **in full**" in _rw, "")
check("report-writer carries the prose standard", "Short paragraphs" in _rw, "")

with open(os.path.join(ROOT, "CLAUDE.md"), encoding="utf-8") as fh:
    _cl = fh.read()
check("the prose standard is stated plugin-wide", "## How a report reads" in _cl, "")

# CLAUDE.md does not reach a forked subagent, so every agent that persists a report carries the
# writing standard itself — and carries the same one, or the reports drift apart in voice.
_WRITERS = ("terminal-analyst", "field-analyst", "desk-analyst", "bull-researcher",
            "bear-researcher", "contest-researcher", "portfolio-manager", "report-writer")
_marker = "- **Cut what carries nothing.** If a sentence would not change what the reader does, delete it."
for stem in _WRITERS:
    with open(os.path.join(ROOT, "agents", stem + ".md"), encoding="utf-8") as fh:
        body = fh.read()
    check(f"{stem} carries the report-writing standard", "## How the report reads" in body, stem)
    check(f"{stem} carries the same wording, not a variant", _marker in body, stem)

summary()
