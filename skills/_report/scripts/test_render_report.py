#!/usr/bin/env python3
"""Standalone tests for the report renderer — house style: offline fixtures, prints
`N passed, M failed`, non-zero exit on failure (bin/test.sh globs skills/**/test_*.py).

Three layers:
  * chart partials — the geometry/formatting/gap-handling contracts in charts.py,
  * render integrity — the fixture renders to a complete 15-slide deck with no template leaks,
  * layout (principles 1/5/7 of the handoff) — a best-effort browser check that SKIPS cleanly
    when no Chrome is present, so the core suite stays fully offline.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))  # skills/_report/scripts -> repo
for p in (_HERE, _REPO):
    if p not in sys.path:
        sys.path.insert(0, p)

from finance.tests import harness  # noqa: E402
from finance.tests.harness import check  # noqa: E402
import charts  # noqa: E402
import render_report  # noqa: E402

FIXTURE = os.path.join(_HERE, "fixtures", "deep-analysis.sample.json")
MF_FIXTURE = os.path.join(_HERE, "fixtures", "mf-analysis.sample.json")


# ── chart partials ────────────────────────────────────────────────────────────────────────────
def test_number_formatting():
    check("indian grouping, lakh", charts.inr_group(123456) == "1,23,456", charts.inr_group(123456))
    check("indian grouping, crore", charts.inr_group(12345678) == "1,23,45,678", charts.inr_group(12345678))
    check("indian grouping, small", charts.inr_group(999) == "999")
    check("inr prefix", charts.inr(123456) == "₹1,23,456")
    check("negative keeps sign", charts.inr_group(-1523) == "-1,523")


def test_bars_fixed_scales_and_gaps():
    html = charts.bars_fixed([100, 50, None, 200], ["A", "B", "C", "D"], plot_h=360)
    # max value fills plot_h-38; the box is the mock's, the data is the run's
    heights = [int(h) for h in re.findall(r"height:(\d+)px;background:", html)]
    check("tallest bar is plot_h-38", max(heights) == 322, heights)
    check("50 scales to a quarter of 200's bar", heights[1] == round(50 / 200 * 322), heights)
    # a None value is a labelled gap, never a zero bar (data-integrity rule)
    check("None renders 'n/a', not a bar", "n/a" in html)
    check("None never renders a zero-height bar", "height:0px;background:" not in html)


def test_svg_text_aspect_rule():
    # handoff §3a: a 1000-wide viewBox in a 1728px box counter-scales text x by 1000/1728
    t = charts._svg_text(50, 100, "9.4", vbw=1000, vbh=130, pxw=1728, pxh=118)
    m = re.search(r"scale\(([\d.]+),([\d.]+)\)", t)
    check("text x-scale = vbw/pxw", harness.approx(float(m.group(1)), 1000 / 1728, 1e-3), m.group(1))
    check("text y-scale = vbh/pxh", harness.approx(float(m.group(2)), 130 / 118, 1e-3), m.group(2))
    check("font-size stays at the 24px floor", 'font-size="24"' in t)


def test_sensitivity_grid_base_outlined():
    cells = [[100, 110, 120], [130, 140, 150], [160, 170, 180]]
    html = charts.sensitivity_grid(["a", "b", "c"], ["x", "y", "z"], cells,
                                   corner="G/W", base_row=1, base_col=1, cmp=200)
    check("base cell is outlined", html.count("outline:3px solid var(--ink)") == 1)
    check("all 9 value cells present", all(str(v) in html for row in cells for v in row))
    check("cells below CMP take a warm tint", "#EAD2C7" in html or "#EFDCD3" in html or "#F2E4DC" in html)


def test_score_ladder_flags_tinted():
    rows = [{"verdict": "PASS", "label": "ok", "detail": "-"},
            {"verdict": "FLAG", "label": "iffy", "detail": "-"}]
    html = charts.score_ladder(rows)
    check("PASS uses the pos colour", "color:#1B6E4F" in html or "var(--pos)" in html)
    check("FLAG row is tinted warn", charts.WARNT in html)
    check("exactly one tinted row", html.count(f"background:{charts.WARNT};") == 1)


def test_peer_bars_priced_and_gap():
    rows = [{"name": "A", "value": 20.0, "pct": 90, "priced": True},
            {"name": "B", "value": None, "pct": 0, "priced": False}]
    html = charts.peer_bars(rows, median_pct=50, median_label="MED 18x")
    check("priced peer shows its multiple", "20.0×" in html)
    check("unpriced peer is 'not priced', never inferred", "not priced" in html)
    check("unpriced peer is hatched, not a solid bar", "repeating-linear-gradient" in html)


def test_stacked_bar_segments_and_legend():
    items = [{"label": "SMALL", "pct": 84.8, "color": "#2C5B8F"},
             {"label": "MID", "pct": 8.1, "color": "#6E90B4"},
             {"label": "LARGE", "pct": 0.3, "color": "#D8D2C6"}]
    html = charts.stacked_bar(items)
    check("widest segment carries an inline label", "SMALL 84.8%" in html)
    check("a sub-threshold segment omits its inline label", html.count("LARGE 0.3%") == 0)
    check("every segment is named in the legend", "LARGE · 0.3%" in html)
    total = 84.8 + 8.1 + 0.3
    check("segment width is the share of the total", f"width:{84.8/total*100:.3f}%" in html)


def test_hbar_list_ranks_and_percent_formats():
    rows = [{"label": "Industrial", "value": 33.2, "color": "#2C5B8F"},
            {"label": "Healthcare", "value": 6.5}]
    html = charts.hbar_list(rows)
    check("value renders as a percent share", "33.2%" in html and "6.5%" in html)
    check("largest bar fills the track", "width:100.0%" in html)
    check("smaller bar scales to its share", f"width:{6.5/33.2*100:.1f}%" in html)


def test_value_build_and_rail():
    rows = [{"label": "PV", "value": "₹144", "left_pct": 0, "width_pct": 34, "color": "#1F3D5C"}]
    vb = charts.value_build(rows)
    check("value-build row carries its bar geometry", "left:0.00%;width:34.00%" in vb)
    rail = charts.percentile_rail(84)
    check("rail marker sits at the percentile", "left:84%" in rail)
    check("rail is the 3-stop gradient", "linear-gradient(90deg,var(--posT)" in rail)


# ── render integrity ──────────────────────────────────────────────────────────────────────────
def _render_fixture(dirpath):
    out = os.path.join(dirpath, "report.html")
    render_report.render(FIXTURE, "deep-analysis", out=out)
    return open(out, encoding="utf-8").read()


def test_render_is_complete_and_clean():
    with tempfile.TemporaryDirectory() as d:
        html = _render_fixture(d)
    check("15 content slides render", len(re.findall(r'data-screen-label="\d\d"', html)) == 15,
          len(re.findall(r'data-screen-label="\d\d"', html)))
    check("no unrendered jinja expressions", "{{" not in html and "{%" not in html)
    check("no leaked python None", ">None<" not in html)
    check("the deck runtime is inlined", "customElements.define('deck-stage'" in html)
    # Regression: deck.js carries a literal "</script>" in a usage comment. If it is
    # inlined un-neutralized the HTML parser closes the <script> there, the component
    # never upgrades, and the deck renders as unscaled, non-navigable full-size slides.
    # The document must therefore contain exactly ONE live "</script>" (the real closing
    # tag) and the comment's copy must be neutralized to "<\/script".
    check("only one live </script> (runtime not truncated)", html.count("</script>") == 1,
          html.count("</script>"))
    check("inlined runtime's </script is neutralized", "<\\/script" in html)
    check("fonts are linked (screen/print deliverable)", "fonts.googleapis.com" in html)
    # Fonts must be EMBEDDED as base64 woff2, not merely CDN-linked: wherever Google
    # Fonts is unreachable a linked-only deck falls back to sans-serif and stops
    # matching the design. Require the @font-face data-URIs to be inlined.
    check("fonts are embedded (base64 woff2), not CDN-only",
          "@font-face" in html and "data:font/woff2;base64," in html)
    check("a sourced value reaches the page", "₹726.95" in html)
    check("₹ is preserved, not mojibake", "₹" in html and "â\x82¹" not in html)


def test_mf_render_is_complete_and_clean():
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "mf.html")
        render_report.render(MF_FIXTURE, "mf-analysis", out=out)
        html = open(out, encoding="utf-8").read()
    check("12 content slides render", len(re.findall(r'data-screen-label="\d\d"', html)) == 12,
          len(re.findall(r'data-screen-label="\d\d"', html)))
    check("no unrendered jinja expressions", "{{" not in html and "{%" not in html)
    check("no leaked python None", ">None<" not in html)
    check("the deck runtime is inlined and neutralized", "customElements.define('deck-stage'" in html
          and html.count("</script>") == 1 and "<\\/script" in html)
    check("fonts are embedded (base64 woff2), not CDN-only",
          "@font-face" in html and "data:font/woff2;base64," in html)
    # a sourced number reaches the page, and the cap-tilt/sector charts render (no treemap collision)
    check("a sourced value reaches the page", "₹12,696 Cr" in html)
    check("cap-tilt stacked bar rendered", "SMALL-CAP · 84.8%" in html)
    check("sector hbar list rendered", "33.2%" in html)
    check("₹ is preserved, not mojibake", "₹" in html and "â\x82¹" not in html)


SECTOR_FIXTURE = os.path.join(_HERE, "fixtures", "sector-analysis.sample.json")


def test_sector_render_is_complete_and_clean():
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "sec.html")
        render_report.render(SECTOR_FIXTURE, "sector-analysis", out=out)
        html = open(out, encoding="utf-8").read()
    check("10 content slides render", len(re.findall(r'data-screen-label="\d\d"', html)) == 10,
          len(re.findall(r'data-screen-label="\d\d"', html)))
    check("no unrendered jinja expressions", "{{" not in html and "{%" not in html)
    check("no leaked python None", ">None<" not in html)
    check("the deck runtime is inlined and neutralized", "customElements.define('deck-stage'" in html
          and html.count("</script>") == 1 and "<\\/script" in html)
    check("fonts are embedded (base64 woff2), not CDN-only",
          "@font-face" in html and "data:font/woff2;base64," in html)
    # the rotation grid classifies by chip and the three deep-dives all rendered
    check("rotation grid value reaches the page", "+45.9%" in html)
    check("all four classifications present", all(k in html for k in ("LEADING", "IMPROVING", "WEAKENING", "LAGGING")))
    check("three deep-dive slides render", len(re.findall(r'data-screen-label="0[567]"', html)) == 3)


WEALTH_FIXTURE = os.path.join(_HERE, "fixtures", "wealth-report.sample.json")


def test_wealth_render_is_complete_and_clean():
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "wealth.html")
        render_report.render(WEALTH_FIXTURE, "wealth-report", out=out)
        html = open(out, encoding="utf-8").read()
    check("8 content slides render", len(re.findall(r'data-screen-label="\d\d"', html)) == 8,
          len(re.findall(r'data-screen-label="\d\d"', html)))
    check("no unrendered jinja expressions", "{{" not in html and "{%" not in html)
    check("no leaked python None", ">None<" not in html)
    check("the deck runtime is inlined and neutralized", "customElements.define('deck-stage'" in html
          and html.count("</script>") == 1 and "<\\/script" in html)
    check("fonts are embedded (base64 woff2), not CDN-only",
          "@font-face" in html and "data:font/woff2;base64," in html)
    # the net-worth spine, the foundation-first verdict and the emergency-fund runway gauge all render
    check("headline net worth reaches the page", "₹1.85 Cr" in html)
    check("foundation-first verdict on the cover", "FOUNDATION FIRST" in html)
    check("emergency-fund runway gauge rendered", "EMERGENCY-FUND RUNWAY" in html and "3.1" in html)
    check("₹ is preserved, not mojibake", "₹" in html and "â\x82¹" not in html)


def test_render_prints_gaps_not_blanks():
    # the fixture's overview treemap, record 10Y series and sector RS series are all absent,
    # so the deck must show a labelled gap in each slot rather than a blank or a fabricated chart.
    with tempfile.TemporaryDirectory() as d:
        html = _render_fixture(d)
    check("missing treemap -> labelled gap", "NOT SEPARATELY DISCLOSED" in html)
    check("missing 10Y series -> labelled gap", "10-YEAR SERIES NOT ON THIS RUN" in html.upper())
    check("missing sector RS series -> labelled gap", "REBASED RS SERIES NOT COMPUTED" in html.upper())
    check("gaps slide is present and titled", "does not know" in html)


# ── layout: handoff §3a principles 1/5/7 (browser-gated, skips offline) ───────────────────────
def _find_chrome():
    for c in ("google-chrome", "chromium", "chromium-browser",
              "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"):
        if os.path.isfile(c) or shutil.which(c):
            return c
    return None


def test_no_slide_overflows_1620():
    """Principle 7: every slide's content must fit the 1620px budget (scrollHeight <= 1620).

    Best-effort: rendered with the fallback font stack (no network) and measured via Chrome's
    --dump-dom, which runs page JS. SKIPS with a note when no Chrome is available so the offline
    suite still passes."""
    chrome = _find_chrome()
    if not chrome:
        print("  note no chrome — overflow check skipped (offline-safe)")
        return
    with tempfile.TemporaryDirectory() as d:
        html = _render_fixture(d)
        css = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
        sections = re.findall(r'(<section [^>]*data-screen-label="\d\d"[^>]*>.*?</section>)', html, re.S)
        # measure each slide at native width, natural height, fallback fonts only (offline)
        blocks = "".join(f'<div class="m" data-i="{i}">{s}</div>' for i, s in enumerate(sections, 1))
        page = (f"<!DOCTYPE html><html><head><meta charset=utf-8><style>{css}"
                ".m{width:1920px;background:#FCFAF6;}.m>section{width:1920px !important;height:auto !important;}"
                "</style></head><body>" + blocks +
                "<script>document.title=[...document.querySelectorAll('.m')]"
                ".map(m=>m.querySelector('section').scrollHeight).join(',');</script></body></html>")
        p = os.path.join(d, "measure.html")
        open(p, "w").write(page)
        try:
            dom = subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
                                  "--virtual-time-budget=4000", "--dump-dom", f"file://{p}"],
                                 capture_output=True, text=True, timeout=60).stdout
        except Exception as e:  # a flaky headless run must not fail the offline suite
            print(f"  note chrome run failed ({e}) — overflow check skipped")
            return
    m = re.search(r"<title>([\d,]+)</title>", dom)
    if not m:
        print("  note chrome returned no measurement — overflow check skipped")
        return
    heights = [int(x) for x in m.group(1).split(",") if x]
    check("measured all 15 slides", len(heights) == 15, heights)
    for i, h in enumerate(heights, 1):
        check(f"slide {i:02d} fits the 1620 budget (scrollHeight {h})", h <= 1620, h)


if __name__ == "__main__":
    harness.run(globals())
