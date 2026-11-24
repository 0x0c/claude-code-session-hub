import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import design_system as ds  # noqa: E402

INDEX = '{"title": "T", "createdOnFiles": {"v": 1}, "lastChange": {"by": "someone"}}'


class DesignSystemTest(unittest.TestCase):
    def setUp(self):
        self.built = ds.build()
        self.lock = {p: ds.digest(t) for p, t in self.built.items()}
        self.live = {**self.built, ds.INDEX: INDEX}

    def plan(self, **kw):
        return ds.make_plan(self.built, kw.get("live", self.live), kw.get("lock", self.lock), kw.get("overwrite", frozenset()))

    def test_build_is_deterministic(self):
        self.assertEqual(ds.build(), self.built)

    def test_a_page_in_step_needs_nothing(self):
        self.assertFalse(any(self.plan().values()))
        # Not even when the lock is lost
        self.assertFalse(any(self.plan(lock={}).values()))

    def test_a_publish_makes_the_next_plan_empty(self):
        old = {"project/README.md": "old", ds.INDEX: INDEX}
        plan = self.plan(live=old, lock={"project/README.md": ds.digest("old")})
        self.assertEqual(plan["update"], ["project/README.md"])
        self.assertEqual(plan["conflict"], [])
        published = {**old, **{p: self.built[p] for p in plan["add"] + plan["update"]}}
        self.assertFalse(any(self.plan(live=published).values()))

    def test_an_edit_on_the_page_is_not_replaced(self):
        path = "project/README.md"
        edited = {**self.live, path: "a person's edit"}
        self.assertEqual(self.plan(live=edited)["conflict"], [path])
        self.assertEqual(self.plan(live=edited, overwrite=frozenset([path]))["update"], [path])

    def test_a_deletion_on_the_page_is_not_undone(self):
        path = "project/README.md"
        live = {p: t for p, t in self.live.items() if p != path}
        self.assertEqual(self.plan(live=live)["conflict"], [path])
        self.assertEqual(self.plan(live=live, overwrite=frozenset([path]))["add"], [path])

    def test_only_our_own_files_are_removed(self):
        live = {**self.live, "project/components/Old/README.md": "ours", "project/notes.md": "theirs"}
        lock = {**self.lock, "project/components/Old/README.md": ds.digest("ours")}
        self.assertEqual(self.plan(live=live, lock=lock),
                         {"add": [], "update": [], "remove": ["project/components/Old/README.md"], "conflict": []})

    def test_the_index_keeps_the_keys_of_the_page(self):
        index = ds.json.loads(ds.next_index(INDEX, "2026-01-01T00:00:00Z"))
        self.assertEqual((index["title"], index["createdOnFiles"]), ("T", {"v": 1}))

    def test_a_second_plan_writes_no_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            live, out, lock = Path(tmp, "live"), Path(tmp, "out"), Path(tmp, "lock.json")
            ds.write(self.live, live)
            with mock.patch.object(ds, "LOCK", lock), mock.patch("builtins.print"):
                args = mock.Mock(live=live, out=out, overwrite=[])
                self.assertEqual(ds.cmd_record(args), 0)
                first = lock.read_bytes()
                self.assertEqual(ds.cmd_plan(args), 0)
                self.assertFalse(out.exists())
                self.assertEqual(ds.cmd_record(args), 0)
                self.assertEqual(lock.read_bytes(), first)

    def run_plan(self, live, lock, overwrite=()):
        """Run the plan command; return its exit code, publish.json, and the files it wrote."""
        with tempfile.TemporaryDirectory() as tmp:
            folder, out, lock_file = Path(tmp, "live"), Path(tmp, "out"), Path(tmp, "lock.json")
            ds.write(live, folder)
            lock_file.write_text(ds.json.dumps(lock), encoding="utf-8")
            out.mkdir()
            (out / "publish.json").write_text("the plan of an earlier run", encoding="utf-8")
            with mock.patch.object(ds, "LOCK", lock_file), mock.patch("builtins.print"):
                code = ds.cmd_plan(mock.Mock(live=folder, out=out, overwrite=list(overwrite)))
            publish = out / "publish.json"
            published = ds.json.loads(publish.read_text(encoding="utf-8")) if publish.exists() else None
            files = {p.relative_to(out).as_posix(): p.read_text(encoding="utf-8")
                     for p in (out / "project").rglob("*") if p.is_file()}
            return code, published, files

    def test_the_plan_command_writes_updates_and_removals(self):
        stale, gone = "project/README.md", "project/components/Old/README.md"
        live = {**self.live, stale: "old", gone: "ours"}
        lock = {**self.lock, stale: ds.digest("old"), gone: ds.digest("ours")}
        code, published, files = self.run_plan(live, lock)
        self.assertEqual(code, 0)
        self.assertEqual(published, {"file_path": ds.INDEX, "files": {stale: stale, gone: None}})
        self.assertEqual(set(files), {stale, ds.INDEX})
        self.assertEqual(files[stale], self.built[stale])
        self.assertNotEqual(files[ds.INDEX], INDEX)

    def test_the_plan_command_writes_nothing_on_a_conflict(self):
        stale, edited = "project/README.md", "project/tokens.json"
        live = {**self.live, stale: "old", edited: "a person's edit"}
        lock = {**self.lock, stale: ds.digest("old")}
        self.assertEqual(self.run_plan(live, lock), (2, None, {}))
        code, published, files = self.run_plan(live, lock, [edited])
        self.assertEqual((code, published["files"]), (0, {stale: stale, edited: edited}))
        self.assertEqual(files[edited], self.built[edited])

    def test_a_token_without_a_description_stops_the_build(self):
        usage = {n: u for n, u in ds.content.USAGE.items() if n != "ink"}
        with mock.patch.object(ds.content, "USAGE", usage), self.assertRaisesRegex(ds.SyncError, "ink"):
            ds.build()

    def test_a_preview_with_an_unknown_class_stops_the_build(self):
        extra = ("Ghost", "Status", 60, '<b class="ghost">x</b>', "s", "r")
        with mock.patch.object(ds.content, "COMPONENTS", [*ds.content.COMPONENTS, extra]), self.assertRaisesRegex(ds.SyncError, "ghost"):
            ds.build()

    def test_every_color_token_is_a_color(self):
        for token in json.loads(self.built["project/tokens.json"])["color"]["tokens"]:
            for value in token["value"].values():
                self.assertRegex(value, r"^(#[0-9a-fA-F]{6}|rgba\(.*\))$", token["name"])

    def test_previews_have_unique_names(self):
        names = [c[0] for c in ds.content.COMPONENTS]
        self.assertEqual(len(names), len(set(names)))


if __name__ == "__main__":
    unittest.main()
