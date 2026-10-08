import copy
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import draft_pr
import scheduled_publish
import test_draft_pr
import test_state_store


class ScheduledPlanTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_draft_pr.DraftTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def fixed_version(self):
        # Same vendor version as stored: an in-place content refresh.
        self.fixture.new["info"]["version"] = "1.0"

    def test_in_place_content_refresh_is_eligible_and_capped(self):
        self.fixed_version()
        report = scheduled_publish.plan_all(self.fixture.base, self.fixture.cache)
        self.assertEqual([e["group"] for e in report["eligible"]], ["example"])
        report = scheduled_publish.plan_all(self.fixture.base, self.fixture.cache, limit=1,
                                            builder=lambda *a: (_ for _ in ()).throw(ValueError("vendor down")))
        self.assertEqual(report["failed"][0]["error_type"], "ValueError")
        self.assertEqual(report["eligible"], [])

    def test_hold_classes_need_manual_review(self):
        cases = {
            "version": lambda new: None,  # fixture default is a new vendor version 2.0
            "removal": lambda new: new["paths"].clear(),
            "auth": lambda new: new.__setitem__("security", [{"other": []}]),
        }
        for name, change in cases.items():
            with self.subTest(case=name):
                self.fixture.new = test_draft_pr.document("2.0" if name == "version" else "1.0")
                self.fixture.new["info"]["description"] = "changed"
                self.fixture.new.setdefault("components", {}).setdefault("securitySchemes", {})["other"] = {"type": "http", "scheme": "bearer"}
                self.fixture.specs["example"] = self.fixture.new
                change(self.fixture.new)
                report = scheduled_publish.plan_all(self.fixture.base, self.fixture.cache)
                self.assertEqual(report["eligible"], [], name)
                self.assertEqual(len(report["needs_manual_review"]), 1, name)

    def test_unchanged_source_and_blocked_source_are_not_eligible(self):
        self.fixture.specs["example"] = self.fixture.old
        self.assertEqual(scheduled_publish.plan_all(self.fixture.base, self.fixture.cache)["matches_source"], ["example"])
        self.fixture.sources[0]["import_blocker"] = "Owner decision pending"
        self.fixture.save_manifest()
        base = self.fixture.commit()
        report = scheduled_publish.plan_all(base, self.fixture.cache)
        self.assertEqual(report["blocked"][0]["group"], "example")
        self.fixture.fetch_mock.reset_mock()


class ScheduledPublishTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_draft_pr.DraftTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.new["info"]["version"] = "1.0"
        self.stores = test_state_store.StateStoreTests(methodName="runTest")
        self.stores.setUp()
        self.addCleanup(self.stores.doCleanups)
        self.entry = {"group": "example", "source": "example"}

    def runner(self, status, blocked=False, raise_error=False):
        def run(plan, args):
            directory = args.cache / plan["group"] / plan["seal"]
            directory.mkdir(parents=True)
            (directory / "candidate.json").write_text(json.dumps({"seal": plan["seal"]}))
            (directory / "result.json").write_text(json.dumps({"status": status}))
            if blocked:
                guard = args.cache / "publication" / plan["group"]
                guard.mkdir(parents=True, exist_ok=True)
                (guard / "blocked.json").write_text('{"stage": "push"}\n')
            if raise_error:
                raise draft_pr.PublicationFailure({"stage": "push"})
            return {"status": status}
        return run

    def test_success_records_receipts_and_releases_lock(self):
        store = self.stores.a
        out = scheduled_publish.publish_all(self.fixture.base, store, [self.entry], runner=self.runner("draft_created"))
        self.assertEqual(out[0]["status"], "draft_created")
        files = store.files(store.head())
        self.assertNotIn("publication/example/publishing.lock", files)
        self.assertTrue(any(k.startswith("publication/example/candidates/") and k.endswith("result.json") for k in files))

    def test_rejected_publication_keeps_guard_and_stops(self):
        store = self.stores.a
        out = scheduled_publish.publish_all(self.fixture.base, store, [self.entry, dict(self.entry)],
                                            runner=self.runner("failed", blocked=True, raise_error=True))
        self.assertEqual(len(out), 1)
        head = store.head()
        self.assertIn("publication/example/blocked.json", store.files(head))
        self.assertFalse(store.available(head, "example")[0])

    def test_unknown_outcome_without_guard_retains_lock(self):
        store = self.stores.a
        out = scheduled_publish.publish_all(self.fixture.base, store, [self.entry],
                                            runner=self.runner("failed", raise_error=True))
        self.assertEqual(out[0]["status"], "interrupted_lock_retained")
        self.assertIn("publication/example/publishing.lock", store.files(store.head()))


if __name__ == "__main__":
    unittest.main()
