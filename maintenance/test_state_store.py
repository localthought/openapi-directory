import subprocess
import tempfile
import unittest
from pathlib import Path

import state_store


class StateStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        base = Path(self.temporary.name)
        self.bare = base / "remote.git"
        subprocess.check_output(["git", "init", "-q", "--bare", str(self.bare)])
        self.a, self.b = self.clone(base / "a"), self.clone(base / "b")
        self.seal = "a" * 64

    def clone(self, path):
        path.mkdir()
        subprocess.check_output(["git", "init", "-q"], cwd=path)
        subprocess.check_output(["git", "remote", "add", "origin", str(self.bare)], cwd=path)
        for key, value in (("user.name", "Fixture"), ("user.email", "fixture@example.com")):
            subprocess.check_output(["git", "config", key, value], cwd=path)
        return state_store.Store(path)

    def test_lock_receipt_release_and_export_layout(self):
        locked = self.a.acquire("example", self.seal)
        self.assertEqual(self.b.head(), locked)
        self.assertEqual(self.b.available(locked, "example")[0], False)
        with self.assertRaises(state_store.StateConflict):
            self.b.acquire("example", "b" * 64)
        released = self.a.release("example", self.seal, locked, {
            "candidates/" + self.seal + "/result.json": b'{"status": "draft_created"}\n',
            "retired/g1.json": b"{}\n"})
        self.assertEqual(self.a.available(released, "example"), (True, None))
        self.assertNotIn("publication/example/publishing.lock", self.a.files(released))
        out = Path(self.temporary.name) / "export"
        self.b.export(self.b.head(), out)
        self.assertTrue((out / "example" / self.seal / "result.json").is_file())
        self.assertTrue((out / "publication/example/retired/g1.json").is_file())
        # History is linear and append-only: lock commit is the parent of the outcome.
        self.assertEqual(self.a.git("rev-parse", released + "^").decode().strip(), locked)

    def test_concurrent_writer_is_rejected_without_overwrite(self):
        first = self.a.acquire("one", self.seal)
        stale = None  # b believes the ref is still absent
        with self.assertRaises(state_store.StateConflict):
            self.b.commit(stale, {"publication/two/publishing.lock": b"x\n"}, "race")
        self.assertEqual(self.a.head(), first)

    def test_append_only_paths_and_lock_ownership(self):
        locked = self.a.acquire("example", self.seal)
        with self.assertRaisesRegex(state_store.StateConflict, "append-only"):
            self.a.commit(locked, {"publication/example/publishing.lock": b"other\n"}, "overwrite")
        with self.assertRaisesRegex(ValueError, "Only an existing publishing.lock"):
            self.a.commit(locked, {}, "drop", removals=["publication/example/other.json"])
        for bad in ("publication/../x", "other/example/x", "publication/Example/x"):
            with self.subTest(path=bad), self.assertRaises(ValueError):
                self.a.commit(locked, {bad: b"x"}, "bad")
        with self.assertRaisesRegex(state_store.StateConflict, "not held"):
            self.a.release("example", "c" * 64, locked, {})

    def test_failure_guard_blocks_until_reviewed_clearance(self):
        locked = self.a.acquire("example", self.seal)
        blocked = self.a.release("example", self.seal, locked, {"blocked.json": b'{"stage": "push"}\n'})
        ok, reason = self.a.available(blocked, "example")
        self.assertFalse(ok)
        self.assertIn("not been cleared", reason)
        with self.assertRaises(state_store.StateConflict):
            self.a.acquire("example", "d" * 64)
        cleared = self.a.commit(blocked, {"publication/example/cleared.json": b'{"reviewed_by": "owner"}\n'}, "clear")
        self.assertEqual(self.a.available(cleared, "example"), (True, None))
        self.assertIn("publication/example/blocked.json", self.a.files(cleared))


if __name__ == "__main__":
    unittest.main()
