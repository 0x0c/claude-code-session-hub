"""Keep the published design system page in step with the dashboard.

    python3 scripts/design_system.py build --out <dir>               # write the generated files
    python3 scripts/design_system.py plan --live <dir> --out <dir>   # say what a sync must publish
    python3 scripts/design_system.py record --live <dir>             # after publishing, update the lock

The design system is a Claude artifact, so an agent reads and publishes its files; this script
decides what to publish. `--live` is the folder that holds a fresh copy of the artifact's project/
folder. Every command is idempotent: the generated files depend on the repository alone, and a plan
against a page that is already in step publishes nothing.

scripts/design_system.lock.json holds the hash of each file we last published. A live file that
differs from both the lock and the build was edited by a person, and the plan refuses to replace it
unless you name it with --overwrite.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import design_system_content as content  # noqa: E402

PAGE = ROOT / "session_hub" / "templates" / "dashboard.html"
LOCK = Path(__file__).resolve().parent / "design_system.lock.json"
INDEX = "project/design-system.json"
FAMILIES = {"spacing": "space-", "radius": "radius-", "fontSize": "fs-", "fontWeight": "fw-"}
FILLS = ("s-", "g-")


class SyncError(Exception):
    pass


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---- Build ----

def declarations(block: str) -> dict[str, str]:
    return {name: value.strip() for name, value in re.findall(r"--([\w-]+):\s*([^;]+);", block)}


def stylesheet() -> tuple[dict[str, str], dict[str, str], str]:
    """The light tokens, the dark tokens, and the rules of the dashboard."""
    style = re.search(r"<style>(.*?)</style>", PAGE.read_text(encoding="utf-8"), re.S)[1]
    head, marker, rules = style.partition("* { box-sizing")
    head = re.sub(r"/\*.*?\*/", "", head, flags=re.S)
    blocks = [declarations(b) for b in re.findall(r":root[^{]*\{([^{}]*)\}", head)]
    if not marker or len(blocks) != 3:
        raise SyncError("the dashboard's token blocks have changed shape")
    # The window-high split layout would pin a component preview to its frame
    rules, removed = re.subn(r"/\* Split layout.*?\n\}\n", "", marker + rules, count=1, flags=re.S)
    if "body:not(.gridlayout)" in rules:
        raise SyncError("the split layout's rules have changed shape")
    return blocks[0], blocks[2], rules.strip() + "\n"


def luminance(color: str) -> float:
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(int(color[i:i + 2], 16) / 255) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def white_contrast(color: str) -> float:
    return 1.05 / (luminance(color) + 0.05)


def plain_color(value: str) -> str:
    """rgb(0 0 0 / .18) in the comma form that the design system page reads."""
    m = re.fullmatch(r"rgb\((\d+) (\d+) (\d+) / ([\d.]+)\)", value)
    return f"rgba({m[1]},{m[2]},{m[3]},{float(m[4])})" if m else value


def build() -> dict[str, str]:
    """Every generated file, by its path in the artifact. The index is not among them."""
    light, dark, rules = stylesheet()
    tokens = {n: v for n, v in light.items() if n != "font-sans"}
    if set(tokens) != set(content.USAGE):
        raise SyncError("scripts/design_system_content.py must describe exactly the stylesheet's tokens; "
                        f"without a description: {sorted(set(tokens) - set(content.USAGE))}; "
                        f"without a token: {sorted(set(content.USAGE) - set(tokens))}")
    unknown = set(re.findall(r'class="([^"]+)"', "".join(c[3] for c in content.COMPONENTS)))
    unknown = {n for names in unknown for n in names.split()} - set(re.findall(r"\.([a-z][\w-]*)", rules))
    if unknown:
        raise SyncError(f"component previews use classes the dashboard no longer has: {sorted(unknown)}")

    colors, weak = [], []
    for name, value in tokens.items():
        if name.startswith(tuple(FAMILIES.values())):
            continue
        usage, pair = content.USAGE[name], (plain_color(value), plain_color(dark.get(name, value)))
        if name.startswith(FILLS) or name == "accent":
            a, b = map(white_contrast, pair)
            usage = usage.rstrip("。") + f"。白文字とのコントラスト：ライト {a:.1f}、ダーク {b:.1f}。"
            if min(a, b) < 4.5:
                usage += "4.5 未満のテーマがある（現行コードの値のまま）。"
                weak.append(f"`{name}`（ライト {a:.1f} / ダーク {b:.1f}）")
        colors.append({"name": name, "value": {"light": pair[0], "dark": pair[1]}, "usage": usage})
    styles = [{"name": n, "fontSize": size, "lineHeight": 1.5, "fontWeight": w, "usage": u, "sample": s}
              for n, size, w, u, s in content.TYPE_STYLES]
    sizes = {v for n, v in tokens.items() if n.startswith("fs-")}
    if {s["fontSize"] for s in styles} != sizes:
        raise SyncError(f"TYPE_STYLES must use exactly the stylesheet's font sizes: {sorted(sizes)}")
    data = {"name": "Session Hub", "version": 1,
            "color": {"themes": [{"id": "light", "name": "Light"}, {"id": "dark", "name": "Dark"}], "tokens": colors},
            "type": {"fonts": [], "families": {"sans": light["font-sans"]},
                     "groups": [{"name": "Text", "family": "sans", "styles": styles}]}}
    for family, prefix in FAMILIES.items():
        data[family] = {"tokens": [{"name": n, "value": v, "usage": content.USAGE[n]}
                                   for n, v in tokens.items() if n.startswith(prefix)]}
    files = {
        "project/tokens.json": json.dumps(data, ensure_ascii=False, indent=1),
        "project/README.md": content.README.replace("{contrast}", "、".join(weak)),
        "project/components/bundle.css": rules,
        "project/components/Cover/preview.html": content.COVER,
    }
    for name, group, height, markup, summary, rule in content.COMPONENTS:
        files[f"project/components/{name}/README.md"] = f"{summary}\n\n{rule}\n"
        files[f"project/components/{name}/preview.html"] = (
            f'<!-- @dsCard group="{group}" height={height} -->\n<!doctype html><html><body>'
            f'<div style="padding:12px;background:var(--panel);color:var(--ink)">{markup}</div></body></html>\n')
    return dict(sorted(files.items()))


def write(files: dict[str, str], out: Path) -> None:
    for path, text in files.items():
        target = out / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


# ---- Plan ----

def read_live(live: Path) -> dict[str, str]:
    """The text files of a live copy. A copy without the index is not a copy of the page."""
    if not (live / INDEX).is_file():
        raise SyncError(f"{live} holds no {INDEX}; read the artifact's project/ files into it first")
    return {p.relative_to(live).as_posix(): p.read_text(encoding="utf-8")
            for p in sorted((live / "project").rglob("*")) if p.suffix in (".md", ".json", ".css", ".html")}


def read_lock() -> dict[str, str]:
    return json.loads(LOCK.read_text(encoding="utf-8")) if LOCK.is_file() else {}


def make_plan(built: dict[str, str], live: dict[str, str], lock: dict[str, str],
              overwrite: frozenset[str] = frozenset()) -> dict[str, list[str]]:
    """What to publish. A path appears in at most one list."""
    plan: dict[str, list[str]] = {"add": [], "update": [], "remove": [], "conflict": []}
    for path, text in built.items():
        if path not in live:
            # A locked file that is gone was deleted on the page
            plan["conflict" if path in lock and path not in overwrite else "add"].append(path)
        elif live[path] != text:
            edited = digest(live[path]) != lock.get(path) and path not in overwrite
            plan["conflict" if edited else "update"].append(path)
    # Only files that we published are ours to remove
    for path in sorted(set(lock) - set(built)):
        if path in live:
            edited = digest(live[path]) != lock[path] and path not in overwrite
            plan["conflict" if edited else "remove"].append(path)
    return plan


def next_index(live_index: str, now: str) -> str:
    """The live index with a new lastChange; every other key stays as the page has it."""
    index = json.loads(live_index)
    index["lastChange"] = {"by": "Claude", "at": now, "via": "scripts/design_system.py",
                           "note": "Synced from session_hub/templates/dashboard.html"}
    return json.dumps(index, ensure_ascii=False)


def cmd_build(a) -> int:
    write(build(), a.out)
    print(f"wrote {a.out}")
    return 0


def cmd_plan(a) -> int:
    built, live = build(), read_live(a.live)
    plan = make_plan(built, live, read_lock(), frozenset(a.overwrite))
    (a.out / "publish.json").unlink(missing_ok=True)  # never leave the plan of an earlier run
    for kind, paths in plan.items():
        for path in paths:
            print(f"{kind:8} {path}")
    if plan["conflict"]:
        print("Edited on the page since the last sync. Carry the edit into the repository, or pass --overwrite <path>.")
        return 2
    if not any(plan.values()):
        print("in step: nothing to publish")
        return 0
    changed = plan["add"] + plan["update"]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    write({p: built[p] for p in changed} | {INDEX: next_index(live[INDEX], now)}, a.out)
    # The `files` input of the publish call; null removes a file. The index goes in as `file_path`.
    files = {p: p for p in changed} | {p: None for p in plan["remove"]}
    (a.out / "publish.json").write_text(json.dumps({"file_path": INDEX, "files": files}, indent=1) + "\n", encoding="utf-8")
    print(f"publish with root {a.out}: see {a.out / 'publish.json'}")
    return 0


def cmd_record(a) -> int:
    built, live = build(), read_live(a.live)
    behind = [p for p in built if live.get(p) != built[p]] + [p for p in set(read_lock()) - set(built) if p in live]
    if behind:
        print("the page is not in step; the lock stays as it was:", *sorted(behind), sep="\n  ")
        return 1
    LOCK.write_text(json.dumps({p: digest(t) for p, t in built.items()}, indent=1) + "\n", encoding="utf-8")
    print(f"recorded {len(built)} files")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Keep the design system page in step with the dashboard")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("build"); s.add_argument("--out", type=Path, required=True); s.set_defaults(run=cmd_build)
    s = sub.add_parser("plan"); s.add_argument("--live", type=Path, required=True)
    s.add_argument("--out", type=Path, required=True)
    s.add_argument("--overwrite", action="append", default=[], metavar="PATH"); s.set_defaults(run=cmd_plan)
    s = sub.add_parser("record"); s.add_argument("--live", type=Path, required=True); s.set_defaults(run=cmd_record)
    a = p.parse_args()
    try:
        return a.run(a)
    except SyncError as e:
        print(f"design_system: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
