#!/usr/bin/env python3
"""Look-through portfolio metrics for the forward-looking pillar (mf-analysis, spec §2).

A fund's own P/E-P/B-ROE aren't exposed by IndMoney, but its holdings + weights are —
so we *compute* them from the underlying stocks' screener.in ratios (`lib/fundamentals.py`,
already whitelisted). Portfolio P/E and P/B aggregate by the **weighted harmonic mean**
(you sum earnings/book yields, not multiples), ROE and earnings growth by weighted mean.
Every figure is reproducible from the cached holdings weights + the cached screener pages.

The math core is pure and offline-tested (`test_lookthrough.py`); only `enrich()` touches
the network. Uncovered weight (unpriced/illiquid holdings) is reported, never extrapolated.

CLI:
  python3 lookthrough.py --holdings holdings.json      # [{symbol, weight}, ...]
"""
from __future__ import annotations

import argparse
import json
import os
import sys

# SEBI classifies caps by market-rank, not absolute size — unknowable from one stock.
# These absolute-₹Cr bands are a labelled approximation of the 2024 cutoffs.
CAP_BANDS_CR = {"large": 50000.0, "mid": 17000.0}  # >=large, >=mid, else small
CAP_TILT_CAVEAT = ("cap-tilt uses approximate absolute market-cap bands (₹Cr); SEBI "
                   "classifies by market rank, so treat the split as indicative.")


def _num(x):
    """Coerce to float; None for anything non-numeric (screener values arrive parsed)."""
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    return None


def _first(d, *keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d[k]
    return None


# --------------------------------------------------------------------------- #
# pure aggregation                                                            #
# --------------------------------------------------------------------------- #
def weighted_harmonic(pairs):
    """(weight, value) → (portfolio multiple, covered weight). Yield-weighted, the
    correct way to aggregate P/E-type multiples. Ignores None / non-positive values."""
    num = cov = 0.0
    for w, v in pairs:
        w, v = _num(w), _num(v)
        if w is None or w <= 0 or v is None or v <= 0:
            continue
        num += w / v
        cov += w
    if num <= 0:
        return None, 0.0
    return cov / num, cov


def weighted_mean(pairs):
    """(weight, value) → (weighted arithmetic mean, covered weight). For ROE/growth,
    which can be negative. Ignores None values."""
    num = cov = 0.0
    for w, v in pairs:
        w, v = _num(w), _num(v)
        if w is None or w <= 0 or v is None:
            continue
        num += w * v
        cov += w
    if cov <= 0:
        return None, 0.0
    return num / cov, cov


def cagr(series):
    """First→last CAGR (%) of a numeric series over len-1 periods. None if <2 usable
    or non-positive endpoints (a sign change makes CAGR meaningless)."""
    xs = [_num(x) for x in (series or []) if _num(x) is not None]
    if len(xs) < 2 or xs[0] <= 0 or xs[-1] <= 0:
        return None
    return ((xs[-1] / xs[0]) ** (1.0 / (len(xs) - 1)) - 1.0) * 100.0


def cap_bucket(mcap_cr):
    m = _num(mcap_cr)
    if m is None:
        return None
    if m >= CAP_BANDS_CR["large"]:
        return "large"
    if m >= CAP_BANDS_CR["mid"]:
        return "mid"
    return "small"


def cap_tilt(holdings):
    """Weight fraction in large/mid/small, over the mcap-covered weight only."""
    buckets = {"large": 0.0, "mid": 0.0, "small": 0.0}
    cov = 0.0
    for h in holdings:
        w = _num(h.get("weight"))
        b = cap_bucket(h.get("mcap"))
        if w is None or w <= 0 or b is None:
            continue
        buckets[b] += w
        cov += w
    if cov <= 0:
        return {"large": None, "mid": None, "small": None, "coverage": 0.0}
    out = {k: round(v / cov, 4) for k, v in buckets.items()}
    out["coverage"] = cov
    return out


def concentration(holdings):
    """Top-5 / top-10 weight and Herfindahl index over the fund's holdings."""
    ws = sorted((_num(h.get("weight")) or 0.0 for h in holdings), reverse=True)
    total = sum(ws)
    if total <= 0:
        return {"n": len(ws), "top5": None, "top10": None, "hhi": None}
    return {
        "n": len(ws),
        "top5": round(sum(ws[:5]) / total, 4),
        "top10": round(sum(ws[:10]) / total, 4),
        "hhi": round(sum((w / total) ** 2 for w in ws), 4),
    }


def portfolio_metrics(holdings):
    """Weighted portfolio ratios + cap-tilt + concentration from enriched holdings,
    each holding carrying weight and (optional) pe/pb/roe/growth/mcap."""
    total = sum(_num(h.get("weight")) or 0.0 for h in holdings)

    def cov(w):
        return round(w / total, 4) if total > 0 else 0.0

    pe, pe_w = weighted_harmonic((h.get("weight"), h.get("pe")) for h in holdings)
    pb, pb_w = weighted_harmonic((h.get("weight"), h.get("pb")) for h in holdings)
    roe, roe_w = weighted_mean((h.get("weight"), h.get("roe")) for h in holdings)
    gro, gro_w = weighted_mean((h.get("weight"), h.get("growth")) for h in holdings)
    return {
        "portfolio_pe": {"value": _round(pe), "coverage": cov(pe_w)},
        "portfolio_pb": {"value": _round(pb), "coverage": cov(pb_w)},
        "portfolio_roe": {"value": _round(roe), "coverage": cov(roe_w)},
        "earnings_growth": {"value": _round(gro), "coverage": cov(gro_w)},
        "cap_tilt": cap_tilt(holdings),
        "concentration": concentration(holdings),
    }


def _round(v, n=2):
    return round(v, n) if isinstance(v, (int, float)) else None


# --------------------------------------------------------------------------- #
# extraction from the screener.in data-pack (pure, fixture-testable)          #
# --------------------------------------------------------------------------- #
def stock_fields(data):
    """screener.in `fetch()` data → {pe, pb, roe, growth, mcap}. Missing → None."""
    r = (data or {}).get("ratios", {}) or {}
    pe = _num(_first(r, "Stock P/E", "Price to Earning", "P/E"))
    mcap = _num(_first(r, "Market Cap", "Market Capitalization"))
    roe = _num(_first(r, "ROE", "Return on equity"))
    pb = _num(_first(r, "Price to Book value", "P/B"))
    if pb is None:  # derive from price / book value when no direct multiple
        price = _num(_first(r, "Current Price", "Price"))
        book = _num(_first(r, "Book Value", "Book Value Per Share"))
        if price is not None and book not in (None, 0):
            pb = price / book
    rows = ((data or {}).get("pnl_10y", {}) or {}).get("rows", {}) or {}
    eps = next((v for k, v in rows.items() if k.lower().startswith("eps")), None)
    growth = cagr(eps) if eps else cagr(rows.get("Net Profit"))
    return {"pe": pe, "pb": _round(pb), "roe": roe, "growth": _round(growth), "mcap": mcap}


# --------------------------------------------------------------------------- #
# network enrichment (not unit-tested — degrade-not-die per holding)          #
# --------------------------------------------------------------------------- #
def enrich(holdings):
    """Fill each holding's ratios from `lib/fundamentals.py`. Returns (holdings, gaps).
    A holding with no resolvable screener symbol, or a failed fetch, keeps its weight
    (so coverage math stays honest) and is named in gaps — never guessed."""
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "..", "..", "..", "lib"))
    import fundamentals  # noqa: E402  (three-dirs-up to the shared data spine)

    gaps = []
    out = []
    for h in holdings:
        sym = _first(h, "symbol", "ticker", "nse_code", "code")
        row = dict(h)
        if not sym:
            gaps.append(f"{_first(h, 'name', 'company') or '?'}: no screener symbol — unpriced")
            out.append(row)
            continue
        env = fundamentals.fetch(sym)
        if not env.get("ok"):
            gaps.append(f"{sym}: fetch failed — unpriced")
            out.append(row)
            continue
        row.update(stock_fields(env.get("data", {})))
        out.append(row)
    return out, gaps


def _load_holdings(payload):
    """Tolerant: accept a bare list or a wrapper with a holdings/data list; each row
    normalised to {symbol, weight, name, ...raw}."""
    rows = payload if isinstance(payload, list) else _first(
        payload, "holdings", "data", "portfolio", "positions") or []
    out = []
    for it in rows:
        if not isinstance(it, dict):
            continue
        out.append({
            "symbol": _first(it, "symbol", "ticker", "nse_code", "code"),
            "name": _first(it, "name", "company", "instrument"),
            "weight": _num(_first(it, "weight", "percentage", "holding_pct",
                                  "corpus_percentage", "pct")),
            **it,
        })
    return out


def main():
    ap = argparse.ArgumentParser(description="Look-through portfolio metrics for a fund.")
    ap.add_argument("--holdings", required=True, help="path to holdings JSON ([{symbol, weight}])")
    args = ap.parse_args()
    with open(args.holdings) as f:
        holdings = _load_holdings(json.load(f))
    enriched, gaps = enrich(holdings)
    metrics = portfolio_metrics(enriched)
    if metrics["cap_tilt"].get("coverage"):
        gaps.append(CAP_TILT_CAVEAT)
    print(json.dumps({"metrics": metrics, "n_holdings": len(enriched), "gaps": gaps}, indent=2))


if __name__ == "__main__":
    main()
