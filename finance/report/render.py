"""report.json + a template -> one self-contained report.html.

Pure compute over the report projection a skill emits (finance/contracts.md → "Artifact:
report projection") and the bundled templates and assets. deck.css, deck.js and the
embedded fonts are inlined so the deck is one file; charts are the data-driven partials in
`charts.py`, never markup authored in a template.
"""
import os
import re
import traceback

from finance import spine
from finance.report import charts

_HERE = os.path.dirname(os.path.abspath(__file__))
_SOURCE = "finance.report.render"
TEMPLATES = os.path.join(_HERE, "templates")
ASSETS = os.path.join(_HERE, "assets")
FIXTURES = os.path.join(_HERE, "fixtures")

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
    # Chart partials return trusted markup the template marks `| safe`; data still auto-escapes.
    for name in dir(charts):
        obj = getattr(charts, name)
        if callable(obj) and not name.startswith("_"):
            env.globals[name] = obj
    env.globals["charts"] = charts
    return env


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
    assets_dir = assets_dir or ASSETS
    templates_dir = templates_dir or TEMPLATES
    data = spine.read_json(report_json)
    if not isinstance(data, dict):
        raise ValueError("report projection must be a JSON object")

    env = _jinja_env(templates_dir)
    with open(os.path.join(assets_dir, "deck.css")) as fh:
        deck_css = fh.read()
    with open(os.path.join(assets_dir, "deck.js")) as fh:
        deck_js = fh.read()
    # A literal "</script" or "</style" in inlined code would close its tag early.
    deck_js = re.sub(r"</(script)", r"<\\/\1", deck_js, flags=re.IGNORECASE)
    deck_css = re.sub(r"</(style)", r"<\\/\1", deck_css, flags=re.IGNORECASE)

    # Embedded fonts render offline; the CDN link covers glyphs outside the bundled subsets.
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

    spine.atomic_write(out, html, fsync=True)
    return out


@spine.guarded(_SOURCE)
def render_report(report_json, template, out=None):
    return spine.envelope(True, _SOURCE, {"report_html": render(report_json, template, out)}, [])
