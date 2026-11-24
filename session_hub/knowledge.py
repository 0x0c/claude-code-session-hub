"""The knowledge summary page: one page that sums up the knowledge collection.

Like the status guide, the page is the dashboard with templates/knowledge.js added inside its script.
The added script reads api/snapshot and counts the built-in "knowledge" collection in the browser.
"""

from __future__ import annotations

from .playbook import build_page


def knowledge_html() -> str:
    return build_page("knowledge.js", "knowledge.css")
