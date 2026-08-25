#!/usr/bin/env python3
"""Offline tests for finance/mcp/_server.py — the bulk-to-disk spill."""
import os
import sys
import tempfile
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

_sdk = types.ModuleType("mcp.server.mcpserver")
_sdk.MCPServer = object
sys.modules.setdefault("mcp", types.ModuleType("mcp"))
sys.modules.setdefault("mcp.server", types.ModuleType("mcp.server"))
sys.modules["mcp.server.mcpserver"] = _sdk

os.environ["EVERYTHING_FINANCE_ARTIFACTS"] = os.path.join(tempfile.mkdtemp(), "artifacts")

import json  # noqa: E402
from finance.mcp import _server  # noqa: E402
from finance.tests.harness import check, run  # noqa: E402

ROWS = [{"i": n} for n in range(50)]


def _env(rows=None):
    return {"ok": True, "source": "test", "fetched_at": "2026-08-21T00:00:00",
            "data": {"positions": ROWS if rows is None else rows}, "gaps": []}


def test_spill_writes_the_complete_list_and_keeps_none_inline():
    out = _server.spill(_env(), "positions", "spill-none")
    check("spill leaves no rows inline by default", out["data"]["positions"] == [])
    check("spill reports the true row count", out["data"]["positions_total"] == 50)
    with open(out["data"]["positions_path"]) as fh:
        check("the file on disk carries every row", json.load(fh) == ROWS)
    check("spill notes where the rest lives",
          "positions_path" in out["data"]["positions_note"],
          out["data"]["positions_note"])


def test_spill_keep_truncates_rather_than_summarising():
    out = _server.spill(_env(), "positions", "spill-keep", keep=3)
    check("spill keeps exactly `keep` rows inline", out["data"]["positions"] == ROWS[:3])
    check("spill keeps the head, not a sample", out["data"]["positions"][0] == {"i": 0})
    check("keep does not change the total", out["data"]["positions_total"] == 50)


def test_spill_shorter_than_keep_adds_no_note():
    out = _server.spill(_env(ROWS[:2]), "positions", "spill-short", keep=10)
    check("a list that fits inline is returned whole", out["data"]["positions"] == ROWS[:2])
    check("nothing was truncated, so there is no note",
          "positions_note" not in out["data"], out["data"].get("positions_note"))


def test_spill_ignores_a_non_list_value():
    env = {"data": {"positions": {"not": "a list"}}, "gaps": []}
    out = _server.spill(env, "positions", "spill-scalar")
    check("a non-list value is left untouched", out["data"]["positions"] == {"not": "a list"})
    check("no _total is invented for it", "positions_total" not in out["data"])


def test_spill_failure_is_a_labelled_gap_not_an_exception():
    orig = _server.paths.cache_dir
    _server.paths.cache_dir = lambda kind: "/nonexistent-volume/does/not/exist"
    try:
        out = _server.spill(_env(), "positions", "spill-fail", keep=2)
    finally:
        _server.paths.cache_dir = orig
    check("a failed spill degrades instead of raising", out["data"]["positions_path"] is None)
    check("the failure is a labelled gap",
          any("could not spill positions" in g for g in out["gaps"]), out["gaps"])
    check("the note tells the reader the rest is a data gap",
          "data gap" in out["data"]["positions_note"], out["data"]["positions_note"])
    check("the rows that survived are still returned", out["data"]["positions"] == ROWS[:2])


def test_safe_name_strips_path_separators():
    check("a slash cannot escape the cache dir",
          _server.safe_name("../../etc/passwd") == ".._.._etc_passwd")
    check("alphanumerics, dash, underscore and dot survive",
          _server.safe_name("NIFTY-50_v1.2") == "NIFTY-50_v1.2")
    check("spaces and punctuation are folded", _server.safe_name("Small Cap: 3y") ==
          "Small_Cap__3y")


if __name__ == "__main__":
    run(globals())
