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
import math
import os
import re
import sys
import tempfile
import traceback

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


def rich_text(value):
    """Allow prose emphasis and line breaks without trusting authored HTML."""
    from html import escape
    from html.parser import HTMLParser
    from urllib.parse import urlsplit
    from markupsafe import Markup

    class Prose(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.output = []

        def handle_starttag(self, tag, attrs):
            if tag == "a":
                href = dict(attrs).get("href", "")
                try:
                    parts = urlsplit(href)
                    valid = parts.scheme in ("https", "http") and bool(parts.netloc)
                except ValueError:
                    valid = False
                self.output.append(f'<a href="{escape(href, quote=True)}" rel="noopener noreferrer">' if valid else '<a>')
            elif tag in ("strong", "em", "b", "i", "br", "code"):
                self.output.append(f"<{tag}>")

        def handle_endtag(self, tag):
            if tag in ("strong", "em", "b", "i", "code", "a"):
                self.output.append(f"</{tag}>")

        def handle_data(self, data):
            self.output.append(escape(data))

    parser = Prose()
    parser.feed(str(value) if value is not None else "")
    parser.close()
    return Markup("".join(parser.output))


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
    env.filters["rich_text"] = rich_text
    # Chart partials + formatting helpers, exposed to the template. Charts return trusted markup,
    # so the template calls them through `| safe`; data values still auto-escape.
    for name in dir(charts):
        obj = getattr(charts, name)
        if callable(obj) and not name.startswith("_"):
            env.globals[name] = obj
    env.globals["charts"] = charts
    return env


def _json_object(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError(f"duplicate report key: {key}")
        obj[key] = value
    return obj


def _json_number(text):
    value = float(text)
    if not math.isfinite(value):
        raise ValueError("report numbers must be finite")
    return value


def _template_line(exc, template):
    """' at <template>.html:<line>' for the deepest template frame, so a projection field that
    breaks the render can be found without re-running under a debugger."""
    frames = [f for f in traceback.extract_tb(exc.__traceback__)
              if f.filename.endswith(f"{template}.html")]
    return f" at {template}.html:{frames[-1].lineno}" if frames else ""


def render(report_json, template, out=None, assets_dir=None, templates_dir=None):
    if not isinstance(template, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", template):
        raise ValueError("template must be a bundled template name")
    out = out or os.path.join(os.path.dirname(os.path.abspath(report_json)), "report.html")
    if os.path.realpath(out) == os.path.realpath(report_json):
        raise ValueError("HTML output cannot overwrite its JSON input")
    assets_dir = assets_dir or os.path.join(_SKILL, "assets")
    templates_dir = templates_dir or os.path.join(_SKILL, "templates")
    with open(report_json) as fh:
        data = json.load(fh, object_pairs_hook=_json_object, parse_float=_json_number,
                         parse_constant=_json_number)
    if not isinstance(data, dict):
        raise ValueError("report projection must be a JSON object")

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

    try:
        tpl = env.get_template(f"{template}.html")
        html = tpl.render(r=data, deck_css=deck_css, deck_js=deck_js,
                          fonts_href=FONTS_HREF, fonts_css=fonts_css)
    except Exception as exc:  # noqa: BLE001 — any failure over untrusted JSON is reported, never raised raw
        raise ValueError(f"report template failed{_template_line(exc, template)}: {exc}. A value "
                         "the work papers lack must be omitted or null so its slot renders a "
                         "labelled gap — never filled with a placeholder") from exc

    pending = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False,
                                         dir=os.path.dirname(os.path.abspath(out))) as fh:
            pending = fh.name
            fh.write(html)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(pending, out)
    finally:
        if pending and os.path.exists(pending):
            os.unlink(pending)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report-json", required=True)
    ap.add_argument("--template", required=True, help="template name without .html (e.g. deep-analysis)")
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    try:
        out = render(args.report_json, args.template, args.out)
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"ok": False, "gaps": [str(exc)]}), file=sys.stderr)
        return 1
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
