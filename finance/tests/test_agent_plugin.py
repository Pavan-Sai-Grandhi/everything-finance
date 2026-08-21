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

summary()
