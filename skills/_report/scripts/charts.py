#!/usr/bin/env python3
"""The chart partials for the report deck — one data-driven generator per chart type.

Every function takes data (series / rows / labels) plus a small size/colour dict and emits
the *exact* inline-SVG / CSS-flex markup the design mock hand-authored. The mock is the pixel
spec: geometry, px heights, colours and type sizes are copied from it and never re-derived; the
only thing that varies per call is the run's own numbers. No chart markup is ever hand-authored
in a template — a template calls one of these.

Pure string builders: no I/O, no network, stdlib only. Covered by test_render_report.py.

Two rules that recur:
  * Bar heights scale the run's real values to a fixed plot box (the box px is the mock's, the
    values are the artifact's), so the *design* matches the mock while the *data* is the run's.
  * Full-width SVGs use preserveAspectRatio="none"; a viewBox W×H rendered into a px box w×h
    stretches type by (w/W, h/H), so every <text> is counter-scaled by (W/w, H/h) — the aspect
    rule in handoff §3a. `_svg_text` does this so labels never stretch.
"""
from html import escape as _e
import math
import re

# ── palette (mirrors deck.css tokens; charts emit literal hex like the mock) ──────────────────
INK = "#1C1F23"; INK2 = "#4A4F56"; INK3 = "#837D74"
RULE = "#E4DFD4"; RULE2 = "#CFC8B9"; PAPER2 = "#F5F2EA"; CARD = "#FFFFFF"
ACCENT = "#2C5B8F"; ACCENTT = "#E9EEF5"
POS = "#1B6E4F"; POST = "#E6EFEA"; NEG = "#A63C2C"; NEGT = "#F7E9E5"
WARN = "#8A6A1F"; WARNT = "#F6EFDF"
BAR = "#2C5B8F"; BAR_MUTED = "#C4BFB2"; EBITDA_GREY = "#D8D2C6"

_MONO = "font-family:var(--mono);"


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _color(value, fallback=BAR):
    return value if isinstance(value, str) and re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", value) else fallback


def _polylines(values, xof, yof, color, width):
    """Keep each contiguous observation run separate; never interpolate a data gap."""
    runs, points = [], []
    for i, value in enumerate(values):
        if value is None:
            if points:
                runs.append(points)
                points = []
        else:
            points.append(f"{xof(i):.1f},{yof(value):.1f}")
    if points:
        runs.append(points)
    return ''.join(f'<polyline points="{" ".join(run)}" fill="none" stroke="{_color(color)}" '
                   f'stroke-width="{width}" vector-effect="non-scaling-stroke"></polyline>' for run in runs)


# ── number formatting (Indian grouping) ──────────────────────────────────────────────────────
def inr_group(n):
    """Indian digit grouping on the integer part: 123456 -> '1,23,456'."""
    neg = n < 0
    s = f"{abs(int(round(n)))}"
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        import re as _re
        head = _re.sub(r"(?<=\d)(?=(\d\d)+$)", ",", head)
        s = head + "," + tail
    return ("-" if neg else "") + s


def inr(n):
    """₹ with Indian grouping, e.g. ₹1,23,456."""
    return "₹" + inr_group(n)


def _fmt(v, spec):
    """Format a value for a bar label given a small spec dict {fmt, unit}."""
    if v is None:
        return "—"
    spec = spec or {}
    kind = spec.get("fmt", "num")
    prec = spec.get("prec", 1)
    if kind == "inr":
        return inr(v)
    if kind == "pct":
        return f"{v:.{prec}f}"
    if kind == "x":
        return f"{v:.1f}×"
    return inr_group(v) if abs(v) >= 1000 else f"{v:g}"


# ── SVG aspect-rule text (handoff §3a) ────────────────────────────────────────────────────────
def _svg_text(x, y, s, *, vbw, vbh, pxw, pxh, size=24, fill=INK3, anchor="start"):
    """A <text> counter-scaled so it renders unstretched inside a preserveAspectRatio='none' SVG."""
    sx = vbw / pxw
    sy = vbh / pxh
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return (f'<text transform="translate({x:.1f},{y:.1f}) scale({sx:.4f},{sy:.4f})" x="0" y="0"{a} '
            f'font-family="IBM Plex Mono, monospace" font-size="{size}" fill="{fill}">{_e(str(s))}</text>')


# ── 1 · fixed-height bar column (revenue / small-multiple) ────────────────────────────────────
def bars_fixed(values, labels, *, plot_h=360, color=BAR, spec=None, gap=14,
               label_color=INK2, title=None):
    """A single bar series in a fixed-height bordered box, value label above each bar, axis below.

    Reference: mock slide 06 (revenue ₹Cr). Bars scale to `plot_h - 38` so the value label and
    its gap always clear the box top. A None value renders a labelled gap column, never a zero bar."""
    vals = [v for v in values if v is not None]
    mx = max(vals) if vals else 1
    maxbar = plot_h - 38
    cells = []
    for v in values:
        if v is None:
            body = ('<span style="' + _MONO + f'font-size:24px;color:{INK3};">n/a</span>'
                    '<div style="width:100%;height:0;"></div>')
        else:
            h = max(1, round(v / mx * maxbar))
            body = ('<span style="' + _MONO + f'font-size:24px;color:{label_color};">{_e(_fmt(v, spec))}</span>'
                    f'<div style="width:100%;height:{h}px;background:{color};"></div>')
        cells.append('<div style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;'
                     f'align-items:center;gap:8px;">{body}</div>')
    axis = "".join('<div style="flex:1;text-align:center;' + _MONO +
                   f'font-size:24px;color:{INK3};">{_e(l)}</div>' for l in labels)
    head = ('<div style="' + _MONO + f'font-size:24px;color:{INK3};letter-spacing:.12em;'
            f'margin-bottom:14px;">{_e(title)}</div>') if title else ""
    return (f'<div style="display:flex;flex-direction:column;">{head}'
            '<div style="position:relative;">'
            f'<div style="display:flex;align-items:flex-end;gap:{gap}px;border-bottom:1px solid var(--rule);'
            f'height:{plot_h}px;">{"".join(cells)}</div></div>'
            f'<div style="display:flex;gap:{gap}px;margin-top:10px;">{axis}</div></div>')


# ── 2 · bar column with a threshold line (ROCE vs WACC) ───────────────────────────────────────
def bars_threshold(values, labels, *, max_bar_px=230, color=BAR, spec=None,
                   threshold=None, threshold_color=NEG, below_color=None, gap=10):
    """Bars scaled so max(values) -> max_bar_px, with an optional dashed threshold line across.

    Reference: mock slide 05 (return on capital vs a WACC dashed line). Bars above the threshold
    keep `color`; below it take `below_color` if given (else `color`)."""
    vals = [v for v in values if v is not None]
    mx = max(vals + ([threshold] if threshold else [])) if vals else 1
    scale = max_bar_px / mx
    cells = []
    for v in values:
        if v is None:
            cells.append('<div style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;'
                         'align-items:center;gap:6px;"><span style="' + _MONO +
                         f'font-size:24px;color:{INK3};">n/a</span></div>')
            continue
        h = max(1, round(v * scale))
        c = below_color if (below_color and threshold and v < threshold) else color
        cells.append('<div style="flex:1;display:flex;flex-direction:column;justify-content:flex-end;'
                     'align-items:center;gap:6px;"><span style="' + _MONO +
                     f'font-size:24px;color:{INK3};">{_e(_fmt(v, spec))}</span>'
                     f'<div style="width:100%;height:{h}px;background:{c};"></div></div>')
    thline = ""
    if threshold is not None:
        tpx = round(threshold * scale)
        thline = (f'<div style="position:absolute;left:0;right:0;bottom:{tpx}px;'
                  f'border-top:2px dashed {threshold_color};"></div>')
    axis = "".join('<div style="flex:1;text-align:center;' + _MONO +
                   f'font-size:24px;color:{INK3};">{_e(l)}</div>' for l in labels)
    return ('<div style="min-height:' + str(max_bar_px) + 'px;display:flex;flex-direction:column;">'
            f'<div style="position:relative;display:flex;align-items:flex-end;gap:{gap}px;'
            f'border-bottom:1px solid var(--rule);">{thline}{"".join(cells)}</div>'
            f'<div style="display:flex;gap:{gap}px;margin-top:10px;">{axis}</div></div>')


# ── 3 · combo nested bars (CFO inside EBITDA) ─────────────────────────────────────────────────
def combo_bars(outer, inner, labels, *, max_bar_px=250, outer_color=EBITDA_GREY,
               inner_color=POS, inner_w="54%", outer_label="EBITDA", inner_label="CASH FROM OPERATIONS"):
    """Two nested series: a wide outer bar with a narrower inner bar centred at its base.

    Reference: mock slide 05 (cash from operations vs EBITDA)."""
    mx = max([v for v in outer if v is not None] or [1])
    scale = max_bar_px / mx
    cells = []
    for o, i in zip(outer, inner):
        oh = max(1, round((o or 0) * scale))
        ih = max(1, round((i or 0) * scale))
        cells.append(f'<div style="flex:1;position:relative;height:{oh}px;background:{outer_color};'
                     'display:flex;justify-content:center;align-items:flex-end;">'
                     f'<div style="width:{inner_w};height:{ih}px;background:{inner_color};"></div></div>')
    axis = "".join('<div style="flex:1;text-align:center;' + _MONO +
                   f'font-size:24px;color:{INK3};">{_e(l)}</div>' for l in labels)
    legend = ('<div style="display:flex;gap:22px;margin-bottom:12px;' + _MONO +
              f'font-size:24px;color:{INK3};">'
              f'<span style="display:inline-flex;align-items:center;gap:8px;"><span style="width:18px;height:18px;'
              f'background:{outer_color};"></span>{_e(outer_label)}</span>'
              f'<span style="display:inline-flex;align-items:center;gap:8px;"><span style="width:18px;height:18px;'
              f'background:{inner_color};"></span>{_e(inner_label)}</span></div>')
    return ('<div style="min-height:230px;display:flex;flex-direction:column;">' + legend +
            '<div style="display:flex;align-items:flex-end;gap:10px;border-bottom:1px solid var(--rule);">'
            f'{"".join(cells)}</div>'
            f'<div style="display:flex;gap:10px;margin-top:10px;">{axis}</div></div>')


# ── 4 · line over a viewBox (margin overlay, RS rebased) ──────────────────────────────────────
def line_svg(series_list, labels, *, px_h=430, vbw=700, vbh=320, baseline=None,
             axis=True, right_labels=None):
    """One or more polylines in a preserveAspectRatio='none' SVG, type counter-scaled per §3a.

    `series_list` is [{values, color, width, dots}]. `right_labels` is [{y_val, text, color}] placed
    at the right edge. Values are mapped to the viewBox with 0 at the given vmin..vmax spread.
    Reference: mock slide 13 (relative strength vs Nifty, rebased)."""
    if (not series_list or not labels or any(
            not isinstance(s, dict) or not isinstance(s.get("values"), (list, tuple))
            or len(s["values"]) != len(labels)
            or any(v is not None and not _finite(v) for v in s["values"])
            for s in series_list)
            or (baseline is not None and not _finite(baseline))):
        return '<p class="data-gap">Line chart unavailable — invalid or misaligned observations.</p>'
    if not any(v is not None for s in series_list for v in s["values"]):
        return '<p class="data-gap">Line chart unavailable — no observations.</p>'
    pxw = 1728  # nominal content width; preserveAspectRatio='none' makes absolute px cancel out
    allvals = [v for s in series_list for v in s["values"] if v is not None]
    if baseline is not None:
        allvals.append(baseline)
    vmin, vmax = (min(allvals), max(allvals)) if allvals else (0, 1)
    if vmax == vmin:
        vmax += 1
    pad = (vmax - vmin) * 0.12
    vmin -= pad; vmax += pad

    def yof(v):
        return vbh - (v - vmin) / (vmax - vmin) * vbh

    n = max(1, len(labels) - 1)
    def xof(i):
        return i / n * vbw
    parts = []
    if baseline is not None:
        yb = yof(baseline)
        parts.append(f'<line x1="0" y1="{yb:.1f}" x2="{vbw}" y2="{yb:.1f}" stroke="{INK3}" '
                     'stroke-width="2" stroke-dasharray="7 5" vector-effect="non-scaling-stroke"></line>')
    for s in series_list:
        color = _color(s.get("color"))
        width = s.get("width", 3)
        width = width if _finite(width) and 0 < width <= 20 else 3
        parts.append(_polylines(s["values"], xof, yof, color, width))
        if s.get("dots"):
            for i, v in enumerate(s["values"]):
                if v is not None:
                    parts.append(f'<circle cx="{xof(i):.1f}" cy="{yof(v):.1f}" r="6" fill="{color}"></circle>')
    for rl in (right_labels or []):
        parts.append(_svg_text(vbw - 6, yof(rl["y_val"]) - 12, rl["text"], vbw=vbw, vbh=vbh,
                               pxw=pxw, pxh=px_h, fill=_color(rl.get("color"), INK3), anchor="end"))
    svg = (f'<svg viewBox="0 0 {vbw} {vbh}" preserveAspectRatio="none" '
           f'style="width:100%;height:{px_h}px;overflow:visible;">{"".join(parts)}</svg>')
    ax = ""
    if axis:
        ax = ('<div style="display:flex;justify-content:space-between;margin-top:14px;' + _MONO +
              f'font-size:24px;color:{INK3};">' +
              "".join(f"<span>{_e(l)}</span>" for l in labels) + "</div>")
    return svg + ax


# ── 5 · value-build (DCF waterfall) ───────────────────────────────────────────────────────────
def value_build(rows):
    """Stacked offset horizontal bars: PV explicit + PV terminal − net debt = fair value.

    `rows` = [{label, value, left_pct, width_pct, color}]. Reference: mock slide 08."""
    out = []
    for r in rows:
        out.append('<div style="display:grid;grid-template-columns:230px 1fr 130px;align-items:center;'
                   'padding:20px 0;border-bottom:1px solid var(--rule);">'
                   '<span style="' + _MONO + f'font-size:24px;letter-spacing:.1em;color:{INK2};">{_e(r["label"])}</span>'
                   '<div style="position:relative;height:34px;">'
                   f'<div style="position:absolute;top:0;bottom:0;left:{r["left_pct"]:.2f}%;'
                   f'width:{r["width_pct"]:.2f}%;background:{r["color"]};"></div></div>'
                   f'<span style="' + _MONO + f'font-size:24px;text-align:right;">{_e(r["value"])}</span></div>')
    return ('<div data-swap-main="" style="flex:1;display:flex;flex-direction:column;'
            'justify-content:space-around;border-top:1px solid var(--rule);">' + "".join(out) + "</div>")


# ── 6 · sensitivity grid (CSS table, tinted cells) ────────────────────────────────────────────
_MOS_TINTS = ["#EAD2C7", "#EFDCD3", "#F2E4DC", "#F4EDE3", "#EDF1EA", "#E2EDE6", "#D7E8DE"]

def _tint(cell_val, cmp):
    """Pick a below/above-CMP tint by how far the cell sits from CMP (mock's warm→cool ramp)."""
    if cmp in (None, 0):
        return "#F4EDE3"
    ratio = (cell_val - cmp) / cmp
    idx = round(3 + max(-3, min(3, ratio / 0.12)))
    return _MOS_TINTS[max(0, min(len(_MOS_TINTS) - 1, idx))]

def sensitivity_grid(row_axis, col_axis, cells, *, corner, base_row, base_col, cmp=None,
                     fmt=lambda v: inr_group(v)):
    """CSS-table sensitivity grid, each cell tinted by distance from CMP, the base case outlined.

    `cells[i][j]` aligns with row_axis[i] × col_axis[j]. Reference: mock slide 08."""
    ncol = len(col_axis)
    head = (f'<div style="padding:18px 16px;' + _MONO + f'font-size:24px;color:{INK3};background:{PAPER2};'
            'border-bottom:1px solid var(--rule);border-right:1px solid var(--rule);">' + _e(corner) + "</div>")
    for c in col_axis:
        head += ('<div style="padding:18px 0;text-align:center;' + _MONO +
                 f'font-size:var(--t-label);background:{PAPER2};border-bottom:1px solid var(--rule);">{_e(c)}</div>')
    body = ""
    last = len(row_axis) - 1
    for i, r in enumerate(row_axis):
        bb = "" if i == last else "border-bottom:1px solid var(--rule);"
        body += ('<div style="padding:20px 16px;' + _MONO + f'font-size:var(--t-label);background:{PAPER2};'
                 f'{bb}border-right:1px solid var(--rule);">{_e(r)}</div>')
        for j in range(ncol):
            v = cells[i][j]
            is_base = (i == base_row and j == base_col)
            tint = _tint(v, cmp)
            style = (f'padding:20px 0;text-align:center;' + _MONO + f'font-size:28px;{bb}background:{tint};')
            if is_base:
                style += "font-weight:600;outline:3px solid var(--ink);outline-offset:-3px;"
            body += f'<div style="{style}">{_e(fmt(v))}</div>'
    return (f'<div style="flex:1;display:grid;grid-template-columns:150px repeat({ncol},1fr);grid-auto-rows:1fr;'
            f'border:1px solid var(--rule);background:{CARD};">{head}{body}</div>')


# ── 7 · percentile rail ───────────────────────────────────────────────────────────────────────
def percentile_rail(pct, *, low="CHEAP", mid="MEDIAN", high="EXPENSIVE", height=28, marker_w=4):
    """A three-stop pos→paper→neg gradient rail with a marker at `pct` (0-100). Position is the read."""
    p = max(0, min(100, pct))
    return ('<div style="position:relative;height:' + str(height) + 'px;'
            'background:linear-gradient(90deg,var(--posT),var(--paper2) 50%,var(--negT));'
            'border:1px solid var(--rule);">'
            f'<div style="position:absolute;left:{p:.0f}%;top:-12px;bottom:-12px;width:{marker_w}px;'
            'background:var(--ink);"></div></div>'
            '<div style="display:flex;justify-content:space-between;' + _MONO +
            f'font-size:24px;color:{INK3};margin-top:14px;">'
            f'<span>{_e(low)}</span><span>{_e(mid)}</span><span>{_e(high)}</span></div>')


# ── 8 · score ladder (integrity / due-diligence checks) ───────────────────────────────────────
_VERDICT_COLOR = {"PASS": POS, "FLAG": WARN, "FAIL": NEG, "NOT-CHECKED": INK3, "n/m": INK3}
_VERDICT_TINT = {"FLAG": WARNT, "FAIL": NEGT}

def score_ladder(rows, *, verdict_w="150px"):
    """PASS / FLAG / FAIL rungs. `rows` = [{verdict, label, detail}]. A flagged row is tinted.

    Per-row flex, not a shared grid: the value hugs the right on a single line at exactly its own
    width, and the label takes the rest of *that* row. A uniform grid column would have to be as wide
    as the longest value and wrap every shorter one; here the long label and long value never share a
    row, so neither wraps. Reference: mock slide 05 (due-diligence scorecard) and slide 07 (integrity gate)."""
    out = ['<div data-swap-main="" style="border-top:1px solid var(--rule);">']
    last = len(rows) - 1
    for k, r in enumerate(rows):
        v = r["verdict"]
        col = _VERDICT_COLOR.get(v, INK3)
        tint = _VERDICT_TINT.get(v)
        bb = "" if k == last else "border-bottom:1px solid var(--rule);"
        rowbg = f"background:{tint};" if tint else ""
        pad = "padding-left:10px;" if tint else ""
        padr = "padding-right:10px;" if tint else ""
        out.append(f'<div style="display:flex;align-items:center;gap:24px;padding:19px 0;{bb}{rowbg}">'
                   f'<span style="flex:0 0 {verdict_w};' + _MONO + f'font-size:24px;font-weight:600;color:{col};letter-spacing:.1em;{pad}">{_e(v)}</span>'
                   f'<span style="flex:1 1 auto;min-width:0;font-size:var(--t-small);">{_e(r["label"])}</span>'
                   '<span style="flex:0 1 auto;white-space:nowrap;text-align:right;' + _MONO + f'font-size:var(--t-small);{padr}">{_e(r.get("detail",""))}</span></div>')
    out.append("</div>")
    return "".join(out)


# ── 10 · candles/close + level bands (technical) ──────────────────────────────────────────────
def candles_levels(closes, ema, levels, *, band=None, cmp_label=None, px_h=630, vbw=1000, vbh=625):
    """Daily close + a moving-average line, horizontal S/R levels, an optional accumulation band.

    `levels` = [{price, kind: 'R'|'S', touches, note, side: 'left'|'right'}]; `band` = {low, high}.
    y maps price to the viewBox over the priced min..max. Reference: mock slide 10."""
    if (not closes or len(ema) != len(closes)
            or not any(v is not None for v in closes)
            or any(v is not None and (not _finite(v) or v <= 0) for v in closes + ema)
            or any(not _finite(l.get("price")) or l["price"] <= 0 for l in levels)
            or (band is not None and (not _finite(band.get("low")) or not _finite(band.get("high"))
                                      or not 0 < band["low"] <= band["high"]))):
        return '<p class="data-gap">Price chart unavailable — invalid or missing observations.</p>'
    pxw = 1728
    allp = [p for p in closes + ema if p is not None] + [l["price"] for l in levels]
    if band:
        allp += [band["low"], band["high"]]
    pmin, pmax = min(allp), max(allp)
    if pmax == pmin:
        pmax += 1
    pad = (pmax - pmin) * 0.10
    pmin -= pad; pmax += pad
    def yof(p):
        return vbh - (p - pmin) / (pmax - pmin) * vbh
    n = max(1, len(closes) - 1)
    def xof(i):
        return i / n * vbw
    parts = []
    if band:
        y1, y2 = yof(band["high"]), yof(band["low"])
        parts.append(f'<rect x="0" y="{y1:.1f}" width="{vbw}" height="{(y2 - y1):.1f}" '
                     f'fill="{POS}" opacity="0.08"></rect>')
    for l in levels:
        y = yof(l["price"])
        col = NEG if l["kind"] == "R" else POS
        w = 2.6 if l.get("emphasis") else (1.6 if l["kind"] == "R" else 2)
        dash = "" if l.get("emphasis") else ' stroke-dasharray="8 6"'
        parts.append(f'<line x1="0" y1="{y:.1f}" x2="{vbw}" y2="{y:.1f}" stroke="{col}" '
                     f'stroke-width="{w}"{dash} vector-effect="non-scaling-stroke"></line>')
    parts.append(_polylines(ema, xof, yof, ACCENT, 3))
    parts.append(_polylines(closes, xof, yof, INK, 4))
    lasty = None
    if closes[-1] is not None:
        lastx = xof(len(closes) - 1)
        lasty = yof(closes[-1])
        parts.append(f'<circle cx="{lastx:.1f}" cy="{lasty:.1f}" r="7" fill="{INK}"></circle>')
    for l in levels:
        y = yof(l["price"])
        col = NEG if l["kind"] == "R" else POS
        side = l.get("side", "right")
        if side == "left":
            parts.append(_svg_text(8, y - 18, l["note"], vbw=vbw, vbh=vbh, pxw=pxw, pxh=px_h,
                                   fill=col, anchor="start"))
        else:
            parts.append(_svg_text(vbw - 8, y - 18, l["note"], vbw=vbw, vbh=vbh, pxw=pxw, pxh=px_h,
                                   fill=col, anchor="end"))
    if cmp_label and lasty is not None:
        parts.append(_svg_text(vbw - 8, lasty - 22, cmp_label, vbw=vbw, vbh=vbh, pxw=pxw, pxh=px_h,
                               size=26, fill=INK, anchor="end"))
    return (f'<svg viewBox="0 0 {vbw} {vbh}" preserveAspectRatio="none" '
            f'style="width:100%;height:{px_h}px;overflow:visible;">{"".join(parts)}</svg>')


# ── 11 · diverging bars (sentiment by fortnight) ──────────────────────────────────────────────
def diverging_bars(values, labels, *, unit_px=40, bar_w="46%", half_h=88):
    """Bars above/below a zero baseline. `values` in −2..+2. Reference: mock slide 11."""
    mx = max([abs(v) for v in values if v is not None] or [1])
    cells = []
    for v, l in zip(values, labels):
        if v is None:
            top = bot = ""
        elif v >= 0:
            h = round(v / mx * (half_h - 24))
            top = (f'<span style="' + _MONO + f'font-size:24px;color:{POS};">+{v:.1f}</span>'
                   f'<div style="width:{bar_w};height:{h}px;background:{POS};"></div>')
            bot = ""
        else:
            h = round(abs(v) / mx * (half_h - 24))
            top = ""
            bot = (f'<div style="width:{bar_w};height:{h}px;background:{NEG};"></div>'
                   f'<span style="' + _MONO + f'font-size:24px;color:{NEG};">{v:.1f}</span>')
        cells.append('<div style="flex:1;display:flex;flex-direction:column;align-items:center;">'
                     f'<div style="height:{half_h}px;display:flex;flex-direction:column;justify-content:flex-end;'
                     f'align-items:center;width:100%;gap:6px;">{top}</div>'
                     '<div style="height:1px;background:var(--ink);width:100%;"></div>'
                     f'<div style="height:{half_h}px;display:flex;flex-direction:column;align-items:center;'
                     f'width:100%;gap:6px;">{bot}</div>'
                     '<div style="' + _MONO + f'font-size:24px;color:{INK3};margin-top:6px;">{_e(l)}</div></div>')
    return f'<div style="display:flex;align-items:flex-end;gap:16px;margin-top:6px;">{"".join(cells)}</div>'


# ── 12 · peer bars (relative P/E vs a median line) ────────────────────────────────────────────
def peer_bars(rows, *, median_pct, median_label):
    """Horizontal multiple bars vs peers, with a dashed median line. A None value is a hatched
    'not priced' row (never inferred). `rows` = [{name, value, pct, priced, focus?}]. Mock slide 09."""
    hatch = ("background:repeating-linear-gradient(45deg,#EFEDE7,#EFEDE7 6px,"
             "#FCFAF6 6px,#FCFAF6 12px);")
    out = [('<div style="flex:1;display:flex;flex-direction:column;justify-content:space-around;'
            'position:relative;border-top:1px solid var(--rule);padding-bottom:44px;">'
            f'<div style="position:absolute;top:0;bottom:44px;left:calc(250px + (100% - 420px) * {median_pct/100:.3f});'
            'border-left:2px dashed var(--neg);"></div>'
            f'<div style="position:absolute;bottom:8px;left:calc(250px + (100% - 420px) * {median_pct/100:.3f} + 10px);'
            + _MONO + f'font-size:24px;color:{NEG};">{_e(median_label)}</div>')]
    for r in rows:
        name_color = INK if r.get("focus") else INK2
        if not r.get("priced", r.get("value") is not None):
            bar = f'<div style="position:absolute;top:0;bottom:0;left:0;width:100%;{hatch}"></div>'
            val = f'<span style="' + _MONO + f'font-size:24px;text-align:right;color:{INK3};">not priced</span>'
        else:
            col = ACCENT if r.get("focus") else BAR_MUTED
            bar = (f'<div style="position:absolute;top:0;bottom:0;left:0;width:{r["pct"]:.1f}%;'
                   f'background:{col};"></div>')
            val = f'<span style="' + _MONO + f'font-size:26px;text-align:right;color:{INK};">{r["value"]:.1f}×</span>'
        out.append('<div style="display:grid;grid-template-columns:250px 1fr 170px;align-items:center;'
                   'padding:16px 0;border-bottom:1px solid var(--rule);">'
                   '<span style="' + _MONO + f'font-size:24px;letter-spacing:.1em;color:{name_color};">{_e(r["name"])}</span>'
                   f'<div style="position:relative;height:32px;">{bar}</div>{val}</div>')
    out.append("</div>")
    return "".join(out)


# ── 13 · horizontal stacked bar (cap-tilt / allocation split) ─────────────────────────────────
def stacked_bar(items, *, height=64, min_label_pct=7.0):
    """One horizontal 100%-wide bar split into coloured segments, with a labelled legend below.

    `items` = [{label, pct, color}] in display order. A segment wide enough (>= min_label_pct)
    carries its label inline in white; every segment is named in the legend. Reference: the Desk
    allocation split — a single clean row where a treemap would over-fragment a few segments."""
    import math
    import re
    if not isinstance(items, list) or not items:
        return '<p class="data-gap">Allocation unavailable.</p>'
    clean = []
    for item in items:
        if not isinstance(item, dict):
            return '<p class="data-gap">Invalid allocation data.</p>'
        pct = item.get("pct")
        if not isinstance(pct, (int, float)) or isinstance(pct, bool) or not math.isfinite(pct) or not 0 <= pct <= 100:
            return '<p class="data-gap">Invalid allocation percentage.</p>'
        color = item.get("color", BAR)
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?", color):
            color = BAR
        clean.append(dict(item, label=str(item.get("label", "Unknown")), color=color))
    total = sum(item["pct"] for item in clean)
    if total > 100.000001:
        return '<p class="data-gap">Allocation exceeds 100%; reconcile overlapping categories.</p>'
    if total < 100:
        clean.append({"label": "Unclassified", "pct": 100 - total, "color": BAR_MUTED})
    items = clean
    segs = []
    for it in items:
        w = it["pct"]
        inside = (f'<span style="{_MONO}font-size:24px;color:#fff;white-space:nowrap;">'
                  f'{_e(it["label"])} {it["pct"]:.1f}%</span>') if it["pct"] >= min_label_pct else ""
        segs.append(f'<div style="box-sizing:border-box;flex-shrink:0;width:{w:.3f}%;background:{it["color"]};display:flex;align-items:center;'
                    f'padding-left:{20 if inside else 0}px;overflow:hidden;">{inside}</div>')
    legend = "".join(
        '<span style="display:inline-flex;align-items:center;gap:10px;' + _MONO +
        f'font-size:24px;color:{INK2};"><span style="width:20px;height:20px;background:{it["color"]};'
        f'display:inline-block;"></span>{_e(it["label"])} · {it["pct"]:.1f}%</span>' for it in items)
    return (f'<div style="display:flex;height:{height}px;border:1px solid var(--rule);overflow:hidden;">'
            f'{"".join(segs)}</div>'
            f'<div style="display:flex;flex-wrap:wrap;gap:32px;margin-top:20px;">{legend}</div>')


# ── 14 · ranked horizontal bars (sector mix / any share list) ─────────────────────────────────
def hbar_list(rows, *, label_w="330px", bar_color=BAR, fmt=lambda v: f"{v:.1f}%"):
    """Ranked horizontal bars: label · proportional bar · value. `rows` = [{label, value, color?}],
    largest first; bars scale to the max value. `fmt` formats the value (percent share by default).
    Reference: the Desk sector-mix list."""
    mx = max([r["value"] for r in rows] or [1])
    out = ['<div style="display:flex;flex-direction:column;gap:14px;">']
    for r in rows:
        w = max(2, r["value"] / mx * 100)
        col = r.get("color", bar_color)
        out.append(f'<div style="display:grid;grid-template-columns:{label_w} 1fr 120px;align-items:center;gap:22px;">'
                   '<span style="' + _MONO + f'font-size:24px;letter-spacing:.06em;color:{INK2};white-space:nowrap;'
                   'overflow:hidden;text-overflow:ellipsis;">' + _e(r["label"]) + '</span>'
                   '<div style="height:30px;background:' + PAPER2 + ';position:relative;">'
                   f'<div style="position:absolute;left:0;top:0;bottom:0;width:{w:.1f}%;background:{col};"></div></div>'
                   '<span style="' + _MONO + f'font-size:26px;text-align:right;">{_e(fmt(r["value"]))}</span></div>')
    out.append("</div>")
    return "".join(out)


# ── 15 · treemap (revenue mix / asset classes) ────────────────────────────────────────────────
def treemap(items, *, height=609, big_w=633):
    """A dominant-block treemap: the largest item as a left block, the rest stacked in a right column.

    `items` = [{label, pct, sub?, color}], largest first. Reference: mock slide 03 (revenue mix)."""
    big = items[0]
    rest = items[1:]
    big_html = (f'<div style="flex:0 0 {big["pct"]:.0f}%;background:{big["color"]};color:#fff;'
                'padding:30px 32px;display:flex;flex-direction:column;justify-content:space-between;'
                f'width:{big_w}px;height:{height}px;">'
                '<div style="' + _MONO + f'font-size:24px;letter-spacing:.14em;">{_e(big["label"])}</div>'
                '<div><div style="' + _MONO + f'font-size:88px;line-height:1;">{big["pct"]:.1f}%</div>'
                + (f'<div style="' + _MONO + f'font-size:24px;color:#A9BDD1;margin-top:10px;">{_e(big.get("sub",""))}</div>'
                   if big.get("sub") else "") + "</div></div>")
    col = ['<div style="flex:1;display:flex;flex-direction:column;gap:4px;">']
    for it in rest:
        col.append(f'<div style="flex:{it["pct"]:.0f};background:{it["color"]};color:#fff;padding:20px 24px;'
                   'display:flex;justify-content:space-between;align-items:center;">'
                   '<div style="' + _MONO + f'font-size:24px;letter-spacing:.12em;">{_e(it["label"])}</div>'
                   '<div style="' + _MONO + f'font-size:28px;">{it["pct"]:.1f}%</div></div>')
    col.append("</div>")
    return f'<div style="min-height:420px;display:flex;gap:4px;">{big_html}{"".join(col)}</div>'


def runway_gauge(months, target_low=3, target_high=6, cap=8):
    """Render assessed runway only; missing inputs never become a zero marker."""
    import math
    values = (months, target_low, target_high, cap)
    if (not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values)
            or months < 0 or not 0 <= target_low <= target_high or cap <= 0):
        return '<p class="data-gap">Runway unavailable — no assessed emergency-reserve estimate.</p>'
    scale = max(cap, target_high, months)
    left = target_low / scale * 100
    width = (target_high - target_low) / scale * 100
    marker = months / scale * 100
    return (f'<div class="runway-gauge" role="img" aria-label="{months:g} months of runway; '
            f'target {target_low:g} to {target_high:g} months">'
            f'<div style="font-family:var(--mono);font-size:52px;">{months:g} mo</div>'
            '<div style="position:relative;height:34px;background:var(--paper2);border:1px solid var(--rule);margin-top:20px;">'
            f'<div style="position:absolute;top:0;bottom:0;left:{left:g}%;width:{width:g}%;background:var(--posT);border-left:1px solid var(--pos);border-right:1px solid var(--pos);"></div>'
            f'<div style="position:absolute;top:-10px;bottom:-10px;left:{marker:g}%;width:4px;transform:translateX(-50%);background:var(--ink);"></div></div>'
            '<div style="display:flex;justify-content:space-between;font-family:var(--mono);font-size:24px;margin-top:14px;">'
            f'<span>0 MO</span><span>{target_low:g}–{target_high:g} MO TARGET</span><span>{scale:g} MO</span></div></div>')
