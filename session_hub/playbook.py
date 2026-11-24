"""The playbook: one page that shows every dashboard component in every state.

The page is the real dashboard (templates/dashboard.html) with the stories of templates/playbook.js
added inside its script, so that a story calls the same render functions as the dashboard does.
"""

from __future__ import annotations

from importlib import resources

from .server import dashboard_html

SNAPSHOT = "/*__HUB_SNAPSHOT__*/null"
END = "})();\n</script>"
EMPTY = '{"sessions":[],"events":[],"total":{},"collections":{},"generated_at":"2026-01-01T00:00:00Z"}'


def template(name: str) -> str:
    return resources.files("session_hub").joinpath("templates", name).read_text(encoding="utf-8")


def _replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"playbook: expected exactly one {old!r} in dashboard.html, found {text.count(old)}")
    return text.replace(old, new)


def build_page(script: str, style: str) -> str:
    """The dashboard in static mode, with the named template script and style added."""
    # An embedded snapshot puts the page in static mode, so it never opens a stream to the hub
    html = _replace_once(dashboard_html(), SNAPSHOT, EMPTY)
    html = _replace_once(html, END, template(script) + END)
    return _replace_once(html, "</head>", f"<style>\n{template(style)}</style>\n</head>")


def playbook_html() -> str:
    return build_page("playbook.js", "playbook.css")
