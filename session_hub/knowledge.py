"""The knowledge page: a searchable list of the knowledge collection, and one item opened in full.

Like the status guide, the page is the dashboard with templates/knowledge.js added inside its script.
The added script reads api/snapshot and filters the built-in "knowledge" collection in the browser.
"""

from __future__ import annotations

from .playbook import build_page


def knowledge_html() -> str:
    return build_page("knowledge.js", "knowledge.css")
