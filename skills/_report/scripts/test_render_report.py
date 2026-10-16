#!/usr/bin/env python3
"""Standalone tests for the report renderer — house style: offline fixtures, prints
`N passed, M failed`, non-zero exit on failure (bin/test.sh globs skills/**/test_*.py).

Three layers:
  * chart partials — the geometry/formatting/gap-handling contracts in charts.py,
  * render integrity — the fixture renders to a complete 15-slide deck with no template leaks,
  * layout (principles 1/5/7 of the handoff) — a best-effort browser check that SKIPS cleanly
    when no Chrome is present, so the core suite stays fully offline.
"""
import json
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
    check("partial coverage preserves absolute percentage width", "width:84.800%" in html)
    check("unclassified remainder remains visible", "Unclassified · 6.8%" in html)


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
    labels = re.findall(r'data-screen-label="(\d\d)"', html)
    check("19 slides render, numbered in order", labels == [f"{i:02d}" for i in range(1, 20)], labels)
    order = [html.find(t) for t in ("Company · origins", "Company · promoters", "Company · today",
                                    "Sector · the growth story", "Sector · standing", "· Valuation<",
                                    "· The debate", "Gaps, sources, papers")]
    check("business, people and sector story come before the numbers and the call",
          -1 not in order and order == sorted(order), order)
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
    check("supplied review verdict renders on the cover", "REVIEW PROTECTION" in html)
    check("emergency-fund runway gauge rendered", "EMERGENCY-FUND RUNWAY" in html and "3.1" in html)
    check("₹ is preserved, not mojibake", "₹" in html and "â\x82¹" not in html)


DAILY_BRIEF_FIXTURE = os.path.join(_HERE, "fixtures", "daily-brief.sample.json")


def test_daily_brief_render_is_complete_and_clean():
    # daily-brief is a single-page phone brief, not a deck: it brings its own styles and needs no
    # deck runtime, so the deck-specific checks (deck-stage slides, inlined </script>) don't apply.
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "brief.html")
        render_report.render(DAILY_BRIEF_FIXTURE, "daily-brief", out=out)
        html = open(out, encoding="utf-8").read()
    check("no unrendered jinja expressions", "{{" not in html and "{%" not in html)
    check("no leaked python None", ">None<" not in html)
    check("single-page brief, not a deck", "deck-stage" not in html and "<section" not in html)
    # the visual language is the Desk system: warm-paper palette + Newsreader/IBM Plex Mono, not the artifact's blue/DM Sans
    check("Desk paper palette in tokens", "--ground:#FCFAF6" in html and "--accent:#2C5B8F" in html)
    check("Desk typefaces (Newsreader + IBM Plex Mono)", "Newsreader" in html and "IBM+Plex+Mono" in html and "DM+Sans" not in html)
    # every section reached the page from its sourced values
    check("index level reaches the page", "24,175" in html)
    check("flows strip rendered", "−₹5,040 Cr" in html and "+₹5,184 Cr" in html)
    check("act alert rendered with its command", "DMART" in html and "/deep-analysis DMART" in html)
    check("authored emphasis passes through (not escaped)", "<strong>SEBI chief</strong>" in html)
    check("position table state pill rendered", "SL-HIT" in html and "pill-slhit" in html)
    check("one-thing rendered", "breaching its ₹3,866" in html)
    check("₹ is preserved, not mojibake", "₹" in html and "â\x82¹" not in html)


def test_changed_since_is_optional_and_renumbers():
    data = json.load(open(FIXTURE))
    data.pop("changed_since")
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "report.json")
        json.dump(data, open(path, "w"))
        html = open(render_report.render(path, "deep-analysis", out=os.path.join(d, "r.html"))).read()
    labels = re.findall(r'data-screen-label="(\d\d)"', html)
    check("no prior run -> no 'what changed' slide, deck renumbers to 18",
          labels == [f"{i:02d}" for i in range(1, 19)] and "Since the last run" not in html, labels)
    check("contents list follows the deck, not authored numbers",
          re.search(r"The story</span><span[^>]*>04<", html), html.count("The story"))


def test_missing_story_band_and_skill_render_as_gaps():
    """The BORORENEW failure: a paper without numeric skill scores or an own-history band made the
    render crash, and the run patched in a placeholder percentile. Each must be a labelled gap."""
    data = json.load(open(FIXTURE))
    data["integrity"]["skill"] = []
    data["relative"]["band"] = {"title": "Own historical band", "pctile_num": None,
                                "gap": {"label": "OWN P/E BAND NOT AVAILABLE",
                                        "text": "Under three years of quarterly EPS."}}
    data["story"]["timeline"] = []
    data["story"]["timeline_gap"] = {"label": "NO DATED MILESTONES", "text": "The report has no journey page."}
    data["people"]["people"] = []
    data["people"]["people_gap"] = {"label": "BOARD PROFILES NOT READ", "text": "No profile section found."}
    data["sector_story"]["policy"] = []
    data["sector_story"]["policy_gap"] = {"label": "NO POLICY DOCUMENT", "text": "No issuing-authority source."}
    data["sector_story"]["risks"] = []
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "report.json")
        json.dump(data, open(path, "w"))
        html = open(render_report.render(path, "deep-analysis", out=os.path.join(d, "r.html"))).read()
    for label in ("SKILL NOT GRADED", "OWN P/E BAND NOT AVAILABLE", "NO DATED MILESTONES",
                  "BOARD PROFILES NOT READ", "NO POLICY DOCUMENT", "None sourced this run"):
        check(f"gap renders: {label}", label in html)
    check("no percentile rail is drawn without a percentile", "var(--paper2) 50%,var(--negT)" not in html)


def test_projection_without_story_slides_renders_labelled_gaps():
    """A mode that skips the sector lens, or a paper with no story section, leaves the key out."""
    data = json.load(open(FIXTURE))
    for key in ("story", "people", "sector_story"):
        data.pop(key)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "report.json")
        json.dump(data, open(path, "w"))
        html = open(render_report.render(path, "deep-analysis", out=os.path.join(d, "r.html"))).read()
    check("each absent story slide keeps its place with a labelled gap",
          html.count("NOT IN THIS RUN") == 3
          and len(re.findall(r'data-screen-label="\d\d"', html)) == 19)


def test_render_failure_names_the_template_line():
    data = json.load(open(FIXTURE))
    data["dcf"]["sensitivity"] = None
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "report.json")
        json.dump(data, open(path, "w"))
        try:
            render_report.render(path, "deep-analysis", out=os.path.join(d, "r.html"))
            msg = ""
        except ValueError as exc:
            msg = str(exc)
    check("a broken field fails with the template line and the gap rule",
          re.search(r"deep-analysis\.html:\d+", msg) and "labelled gap" in msg, msg)


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


def test_browser_report_layout():
    """Opt-in actual runtime test; requested checks fail rather than silently skip.

    EF_REPORT_BROWSER_CHECK=1 enables this check. Node must resolve Playwright
    (NODE_PATH may point at an installed runtime); EF_REPORT_NODE selects Node.
    """
    if os.environ.get("EF_REPORT_BROWSER_CHECK") != "1":
        print("  note browser integration not requested (set EF_REPORT_BROWSER_CHECK=1)")
        return
    chrome = _find_chrome()
    if not chrome:
        raise RuntimeError("browser verification requested but Chrome is unavailable")
    with tempfile.TemporaryDirectory() as d:
        for name in ("deep-analysis", "wealth-report", "mf-analysis", "sector-analysis", "daily-brief"):
            render_report.render(os.path.join(_HERE, "fixtures", name + ".sample.json"), name,
                                 out=os.path.join(d, name + ".html"))
        result = subprocess.run([os.environ.get("EF_REPORT_NODE", "node"),
                                 os.path.join(_HERE, "check_report_layout.cjs"), d, chrome],
                                capture_output=True, text=True, timeout=60)
        check("actual browser scrolling, navigation and print layout", result.returncode == 0,
              result.stdout + result.stderr)


def test_wealth_runway_missing_and_scaled():
    import json
    check('missing runway renders a labelled gap', 'Runway unavailable' in charts.runway_gauge(None))
    check('zero gauge cap renders a gap', 'Runway unavailable' in charts.runway_gauge(2, cap=0))
    check('long runway expands scale instead of leaving slide', 'left:100%' in charts.runway_gauge(20) and '20 MO' in charts.runway_gauge(20))
    check('gauge label follows supplied target', '2–4 MO TARGET' in charts.runway_gauge(3, 2, 4))
    with open(os.path.join(_HERE, 'fixtures', 'wealth-report.sample.json')) as stream:
        data = json.load(stream)
    data['cross']['ef']['months'] = None
    data['gaps']['disclaimer'] = '<img src=x onerror=alert(1)>'
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'report.json')
        with open(path, 'w') as stream:
            json.dump(data, stream)
        html = open(render_report.render(path, 'wealth-report')).read()
    check('wealth deck renders missing runway without arithmetic exception', 'Runway unavailable' in html)
    check('wealth disclaimer remains escaped data', '<img src=x onerror=alert(1)>' not in html and '&lt;img' in html)


def test_report_prose_and_allocation_boundaries():
    unsafe = '<strong onclick="alert(1)">Fact</strong><script>alert(2)</script><img src=x onerror=alert(3)><a href="javascript:alert(4)">link</a>'
    rendered = str(render_report.rich_text(unsafe))
    check('prose formatting preserves emphasis', '<strong>Fact</strong>' in rendered)
    check('prose cannot create executable tags or attributes', all(token not in rendered for token in ('<script', '<img', 'onclick', 'javascript:')))
    linked = str(render_report.rich_text('<a href="https://example.com/filing?a=1&amp;b=2">filing</a>'))
    check('source hyperlinks survive restricted formatting', 'href="https://example.com/filing?a=1&amp;b=2"' in linked)
    for items in ([], [{'label': 'A', 'pct': -1}], [{'label': 'A', 'pct': float('nan')}], [{'label': 'A', 'pct': 101}]):
        check('invalid allocation renders a gap', 'data-gap' in charts.stacked_bar(items))
    rendered = charts.stacked_bar([{'label': '<img>', 'pct': 40, 'color': 'red;" onmouseover="alert(1)'}])
    check('chart color cannot escape its attribute', 'onmouseover' not in rendered)
    check('chart labels remain escaped', '&lt;img&gt;' in rendered and '<img>' not in rendered)


def test_report_publication_integrity():
    from unittest.mock import patch
    with tempfile.TemporaryDirectory() as tmp:
        output = os.path.join(tmp, 'existing.html')
        with open(output, 'w') as stream:
            stream.write('prior complete report')
        with patch.object(render_report.os, 'replace', side_effect=OSError('simulated failure')):
            try:
                render_report.render(FIXTURE, 'deep-analysis', out=output)
            except OSError:
                pass
        check('failed publication preserves existing report', open(output).read() == 'prior complete report')
        check('failed publication leaves no temporary file', os.listdir(tmp) == ['existing.html'])
        path = os.path.join(tmp, 'input.json')
        for bad in ('[]', '{"x": NaN}', '{"x": 1e999}', '{"x": 1, "x": 2}'):
            with open(path, 'w') as stream:
                stream.write(bad)
            try:
                render_report.render(path, 'deep-analysis', out=output)
                rejected = False
            except ValueError:
                rejected = True
            check('invalid projection rejected before publication', rejected and open(output).read() == 'prior complete report')
        with open(path, 'w') as stream:
            stream.write('{}')
        try:
            render_report.render(path, 'deep-analysis', out=path)
            rejected = False
        except ValueError:
            rejected = True
        check('output cannot replace its own source JSON', rejected and open(path).read() == '{}')


def test_line_chart_missing_observations():
    series = [{'values': [10, 12, None, 14, 15], 'color': charts.BAR}]
    html = charts.line_svg(series, ['a', 'b', 'c', 'd', 'e'])
    check('line breaks at missing observations', html.count('<polyline ') == 2)
    html = charts.candles_levels([10, 12, None, 14, None], [None, 11, None, 13, None], [])
    check('missing latest close has no current-price marker', '<circle ' not in html)
    check('technical close line breaks at missing observations', html.count('stroke="' + charts.INK + '"') == 2)
    check('empty technical chart is a labelled gap', 'data-gap' in charts.candles_levels([], [], []))
    check('unobserved line is a labelled gap', 'data-gap' in charts.line_svg([{'values': [None], 'color': charts.BAR}], ['a']))
    html = charts.line_svg([{'values': [1, 2], 'color': '\" onload=\"alert(1)'}], ['a', 'b'])
    check('line color cannot inject SVG attributes', 'onload' not in html)


if __name__ == "__main__":
    harness.run(globals())
