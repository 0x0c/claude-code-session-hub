"""The status guide: one page that explains every status and state.

The page is the dashboard with templates/guide.js added inside its script, so that the guide and the
dashboard's help icons read the same explanations.
"""

from __future__ import annotations

from .playbook import build_page


def guide_html() -> str:
    return build_page("guide.js", "guide.css")
