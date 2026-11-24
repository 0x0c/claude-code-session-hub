"""Write the playbook to a file, to read it without a hub.

    python3 scripts/playbook.py [--out playbook.html]

A running hub serves the same page at /playbook.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from session_hub.playbook import playbook_html  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description="Write the dashboard playbook to a file")
    p.add_argument("--out", type=Path, default=ROOT / "playbook.html")
    args = p.parse_args()
    args.out.write_text(playbook_html(), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
