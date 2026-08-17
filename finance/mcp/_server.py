#!/usr/bin/env python3
"""Shared plumbing for the three finance MCP servers (`market`, `company`, `funds`).

A server module is declaration and delegation only: it names its tools and hands each one
straight to `finance/`. The library holds every decision — filtering, ranking, envelope
assembly — so a skill script and a tool return the same numbers by construction.

`spill` and `safe_name` are the one concern that belongs here rather than in the library:
a tool answers a model with a finite context window, so bulk rows go to disk and only a
summary plus the path comes back.

This package is `finance.mcp`. A top-level `mcp/` package in the repo would shadow the
installed MCP SDK for every import in the process — the same trap that keeps the shared
HTTP layer named `transport`.
"""
from __future__ import annotations

import json
import os

from finance import paths

from mcp.server.mcpserver import MCPServer

VERSION = "1.0.0"

# The two facts a caller cannot read off a tool schema. Every server states them.
PROTOCOL = (
    "Bulk results are written to a file and the response carries `<key>_path`: read that "
    "file for the rest — never re-call a tool to page through data it already wrote. Every "
    "tool returns {ok, source, fetched_at, data, gaps}; a non-empty `gaps` is a labelled "
    "degradation to report, not an error to retry."
)


def create(name, instructions):
    """The server object a module's tools attach to."""
    return MCPServer(name=name, version=VERSION,
                     instructions=f"{instructions} {PROTOCOL}")


def spill(env, key, name, keep=0):
    """Move a bulk list out of the response and onto disk.

    Returns the envelope with `data[key]` cut to at most `keep` rows plus
    `data[key + "_total"]` and `data[key + "_path"]` — what keeps a 278-row holdings list
    or a 3,350-row NAV series out of a context window while leaving the complete data on
    disk for any script that needs it.
    """
    rows = (env.get("data") or {}).get(key)
    if not isinstance(rows, list):
        return env
    path = os.path.join(paths.cache_dir("mcp"), f"{name}.json")
    try:
        with open(path, "w") as fh:
            json.dump(rows, fh, ensure_ascii=False)
    except OSError as exc:
        env.setdefault("gaps", []).append(f"could not spill {key} to disk: {exc}")
        path = None
    env["data"][key] = rows[:keep]
    env["data"][f"{key}_total"] = len(rows)
    env["data"][f"{key}_path"] = path
    if len(rows) > keep:
        env["data"][f"{key}_note"] = (
            f"{len(rows)} rows written to {key}_path; {keep} shown. Read the file for the "
            f"rest — it is the complete list, never re-fetch to page through it."
            if path else
            f"{len(rows)} rows found but the spill failed; only {keep} are available here "
            f"and there is no file to read. Treat the rest as a data gap."
        )
    return env


def safe_name(name):
    """Filesystem-safe fragment for a spill filename."""
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in str(name))
