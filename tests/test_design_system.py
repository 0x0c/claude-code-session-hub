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

    def test_a_token_without_a_description_stops_the_build(self):
        usage = {n: u for n, u in ds.content.USAGE.items() if n != "ink"}
        with mock.patch.object(ds.content, "USAGE", usage), self.assertRaisesRegex(ds.SyncError, "ink"):
            ds.build()

    def test_a_preview_with_an_unknown_class_stops_the_build(self):
        extra = ("Ghost", "Status", 60, '<b class="ghost">x</b>', "s", "r")
        with mock.patch.object(ds.content, "COMPONENTS", [*ds.content.COMPONENTS, extra]), self.assertRaisesRegex(ds.SyncError, "ghost"):
            ds.build()

    def test_previews_have_unique_names(self):
        names = [c[0] for c in ds.content.COMPONENTS]
        self.assertEqual(len(names), len(set(names)))


if __name__ == "__main__":
    unittest.main()
