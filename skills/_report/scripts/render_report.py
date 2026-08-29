#!/usr/bin/env python3
"""report.json + a template -> one self-contained report.html.

Pure compute over a local JSON file (the report projection the skill emits) and the bundled
template/assets — it fetches nothing, exactly like every other skill script. It inlines deck.css
and deck.js so the deck is one file; type comes from a Google Fonts link (the deck is a screen/
print deliverable, not an offline artifact). Charts are the data-driven partials in charts.py —
no chart markup is authored in a template.

Usage:
    render_report.py --report-json <path> --template deep-analysis [--out <path>]

`report.json` is a *render input with no consumer* (finance/contracts.md → "Artifact: report
projection"). Nothing in the plugin ever reads it back into a decision.
"""
import argparse
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SKILL = os.path.dirname(_HERE)
_REPO = os.path.dirname(os.path.dirname(_SKILL))
for p in (_HERE, _REPO):
    if p not in sys.path:
        sys.path.insert(0, p)

import charts  # noqa: E402  (bundled beside this script)

FONTS_HREF = ("https://fonts.googleapis.com/css2?"
              "family=Newsreader:ital,opsz,wght@0,6..72,300;0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400"
              "&family=IBM+Plex+Mono:wght@400;500;600&display=swap")


def _jinja_env(templates_dir):
    from finance.deps import need
    need("jinja2")
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    # Chart partials + formatting helpers, exposed to the template. Charts return trusted markup,
    # so the template calls them through `| safe`; data values still auto-escape.
    for name in dir(charts):
        obj = getattr(charts, name)
        if callable(obj) and not name.startswith("_"):
            env.globals[name] = obj
    env.globals["charts"] = charts
    return env


def render(report_json, template, out=None, assets_dir=None, templates_dir=None):
    assets_dir = assets_dir or os.path.join(_SKILL, "assets")
    templates_dir = templates_dir or os.path.join(_SKILL, "templates")
    with open(report_json) as fh:
        data = json.load(fh)

    env = _jinja_env(templates_dir)
    with open(os.path.join(assets_dir, "deck.css")) as fh:
        deck_css = fh.read()
    with open(os.path.join(assets_dir, "deck.js")) as fh:
        deck_js = fh.read()
    # Inlining into <script> must neutralize any literal "</script" (deck.js
    # carries one in a usage comment) — otherwise the HTML parser closes the
    # script tag there and customElements.define never runs, leaving the deck
    # as unscaled, non-navigable full-size sections. "<\/" is inert in JS.
    deck_js = re.sub(r"</(script)", r"<\\/\1", deck_js, flags=re.IGNORECASE)
    # Same hazard for inlined CSS, though deck.css is unlikely to carry it.
    deck_css = re.sub(r"</(style)", r"<\\/\1", deck_css, flags=re.IGNORECASE)

    # Fonts are embedded (base64 woff2) so the deck matches the design exactly
    # even with no network — the CDN <link> is kept only as an online fallback
    # for any glyph outside the bundled latin/latin-ext subsets. Without this the
    # deck falls back to sans-serif wherever Google Fonts is unreachable.
    fonts_css = ""
    fonts_path = os.path.join(assets_dir, "fonts.css")
    if os.path.exists(fonts_path):
        with open(fonts_path) as fh:
            fonts_css = re.sub(r"</(style)", r"<\\/\1", fh.read(), flags=re.IGNORECASE)

    tpl = env.get_template(f"{template}.html")
    html = tpl.render(r=data, deck_css=deck_css, deck_js=deck_js,
                      fonts_href=FONTS_HREF, fonts_css=fonts_css)

    out = out or os.path.join(os.path.dirname(os.path.abspath(report_json)), "report.html")
    with open(out, "w") as fh:
        fh.write(html)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report-json", required=True)
    ap.add_argument("--template", required=True, help="template name without .html (e.g. deep-analysis)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    out = render(args.report_json, args.template, args.out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
