import contextlib
import copy
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import draft_pr
import pending_pr
import refresh_pr
import test_pending_pr
import update


class RefreshTests(unittest.TestCase):
    def setUp(self):
        self.pending = test_pending_pr.PendingTests(methodName="runTest")
        self.pending.setUp()
        self.addCleanup(self.pending.doCleanups)
        self.fixture = self.pending.fixture
        self.fixture.remote()
        self.fixture.git("push", "origin", self.pending.head + ":refs/heads/" + self.pending.old["branch"])
        self.fixture.new["paths"]["/items/{id}"]["get"]["responses"]["200"]["description"] = "Fresh vendor response"
        self.guard = patch.object(draft_pr, "remote_guard")
        self.remote = self.guard.start()
        self.addCleanup(self.guard.stop)
        self.original_git = draft_pr.git
        git_patch = patch.object(draft_pr, "git", side_effect=self.git)
        self.git_mock = git_patch.start()
        self.addCleanup(git_patch.stop)
        self.after_push = None
        self.fresh = self.fixture.cache / "fresh"

    def git(self, *args, **kwargs):
        result = self.original_git(*args, **kwargs)
        if args[0] == "push":
            head = self.fixture.git("rev-parse", "--verify", args[-1].split(":")[0])
            self.pending.pr["head"]["sha"] = head
            self.pending.pr["updated_at"] = "2026-10-08T11:00:00Z"
            files = self.fixture.git("diff-tree", "--no-commit-id", "--name-only", "-r", self.fixture.base, head).splitlines()
            self.pending.files = [{"filename": p} for p in files]
            self.pending.pr["changed_files"] = len(files)
            self.pending.matches[0]["head"] = head
            if self.after_push:
                self.after_push()
        return result

    def run_refresh(self):
        return refresh_pr.refresh(self.fixture.plan(), self.fresh, self.fixture.cache)

    def no_push(self):
        self.assertFalse(any(c.args[0] == "push" for c in self.git_mock.call_args_list))

    def test_real_exact_head_lease_update_preserves_text_index_and_success_history(self):
        original = copy.deepcopy(self.pending.pr)
        before = (self.fixture.git("status", "--porcelain"), self.fixture.git("diff", "--cached"), self.fixture.git("rev-parse", "HEAD"))
        result = self.run_refresh()
        self.assertEqual(result["status"], "draft_updated")
        self.assertEqual(result["previous_head"], original["head"]["sha"])
        self.assertEqual(self.pending.pr["body"], original["body"])
        self.assertEqual(self.pending.pr["title"], original["title"])
        self.assertEqual(self.fixture.git("ls-remote", "origin", "refs/heads/" + self.pending.old["branch"]).split()[0], result["head"])
        self.assertEqual(before, (self.fixture.git("status", "--porcelain"), self.fixture.git("diff", "--cached"), self.fixture.git("rev-parse", "HEAD")))
        self.assertEqual(json.loads((self.pending.directory / "result.json").read_text())["status"], "draft_created")
        review = pending_pr.review(self.fixture.plan(), self.fixture.cache)
        self.assertEqual(review["status"], "pending_matches_source")
        self.assertEqual(review["creation_candidate_sha256"], self.pending.old["seal"])
        self.assertIs(review["publication_authorized"], False)
        push = next(c for c in self.git_mock.call_args_list if c.args[0] == "push")
        self.assertIn("--force-with-lease=refs/heads/" + self.pending.old["branch"] + ":" + original["head"]["sha"], push.args)

    def test_two_refreshes_keep_an_intact_bounded_chain_to_original_submission(self):
        first = self.run_refresh()
        self.fixture.new["paths"]["/items/{id}"]["get"]["responses"]["200"]["description"] = "Second vendor response"
        second = self.run_refresh()
        self.assertEqual(second["status"], "draft_updated")
        self.assertEqual(second["previous_head"], first["head"])
        self.assertEqual(second["previous_candidate_sha256"], first["candidate_sha256"])
        self.assertEqual(second["creation_candidate_sha256"], self.pending.old["seal"])
        self.assertEqual(pending_pr.review(self.fixture.plan(), self.fixture.cache)["status"], "pending_matches_source")
        previous = self.fixture.cache / self.pending.old["group"] / first["candidate_sha256"] / "result.json"
        data = json.loads(previous.read_text())
        data["previous_head"] = "a" * 40
        previous.write_text(json.dumps(data))
        self.assertEqual(pending_pr.review(self.fixture.plan(), self.fixture.cache)["status"], "held")

    def test_offline_summary_reports_current_head_provenance_and_main_comparison(self):
        result = self.run_refresh()
        self.fixture.fetch_mock.reset_mock()
        self.pending.gh.reset_mock()
        summary = draft_pr.validate_commit(self.fixture.base, result["head"], self.pending.old["branch"])
        self.assertEqual(summary["head"], result["head"])
        row = summary["comparisons_from_main"][0]
        self.assertEqual(row["stored"]["version"], "1.0")
        self.assertEqual(row["source"]["version"], "2.0")
        expected = update.stored(row["destination"], result["head"])
        self.assertEqual(row["origin"], expected["info"]["x-origin"])
        raw, metadata = self.fixture.fetch(self.fixture.sources[0])
        self.assertEqual(row["conversion"], expected["info"]["x-conversion"])
        self.assertIn(metadata["sha256"], json.dumps(row["conversion"]))
        self.fixture.fetch_mock.assert_not_called()
        self.pending.gh.assert_not_called()

    def test_companions_refresh_together_and_one_invalid_member_prevents_push(self):
        f = self.fixture
        f.sources[0]["publication_group"] = "example-public"
        f.sources.append({**copy.deepcopy(f.sources[0]), "id": "example-dated",
                          "target": "APIs/example.com/dated/1.0/openapi.yaml"})
        f.specs["example-dated"] = copy.deepcopy(f.new)
        f.save_manifest()
        f.base = f.commit()
        self.pending.old = f.plan()
        self.pending.head = draft_pr.commit_plan(self.pending.old)
        self.pending.pr["head"].update(sha=self.pending.head, ref=self.pending.old["branch"])
        self.pending.pr["base"]["sha"] = f.base
        self.pending.pr.update(title="Update official example-public API", body=draft_pr.pr_body(self.pending.old),
                               changed_files=len(self.pending.old["files"]))
        self.pending.matches[0]["head"] = self.pending.head
        self.pending.files = [{"filename": p} for p in self.pending.old["files"]]
        self.pending.receipt()
        f.git("push", "origin", self.pending.head + ":refs/heads/" + self.pending.old["branch"])
        f.specs["example-dated"]["paths"]["/items/{id}"]["get"]["responses"]["200"]["description"] = "Companion refresh"
        self.assertEqual([c["status"] for c in pending_pr.review(f.plan(), f.cache)["comparisons_from_pending"]],
                         ["matches_source", "changed"])
        result = self.run_refresh()
        self.assertEqual(result["status"], "draft_updated")
        self.assertEqual(len(result["files"]), 3)
        self.assertEqual(len(pending_pr.review(f.plan(), f.cache)["comparisons_from_pending"]), 2)
        f.specs["example-dated"]["components"]["schemas"]["Choice"]["oneOf"] = []
        self.git_mock.reset_mock()
        with self.assertRaisesRegex(ValueError, "validation failed"):
            self.run_refresh()
        self.no_push()

    def test_callback_change_requires_deliberate_reconciliation(self):
        callback = {"{$request.query.callbackUrl}": {"post": {"responses": {"200": {"description": "Accepted"}}}}}
        self.fixture.new["paths"]["/items/{id}"]["get"]["callbacks"] = {"notify": callback}
        result = self.run_refresh()
        self.assertEqual(result["status"], "held")
        self.assertIn("callback", result["reason"])
        self.no_push()

    def test_legacy_submission_is_readable_but_not_automatically_rewritten(self):
        old = self.pending.old
        old.pop("publication_protocol")
        old["seal"] = draft_pr.seal(old)
        self.pending.head = draft_pr.commit_plan(old)
        self.pending.pr["head"]["sha"] = self.pending.head
        self.pending.pr["body"] = draft_pr.pr_body(old)
        self.pending.matches[0]["head"] = self.pending.head
        self.pending.receipt()
        self.assertEqual(pending_pr.review(self.fixture.plan(), self.fixture.cache)["status"], "pending_refresh_requires_review")
        result = self.run_refresh()
        self.assertEqual(result["status"], "held")
        self.assertIn("Legacy", result["reason"])
        self.no_push()

    def test_main_advance_never_automatically_rebases_even_if_unrelated(self):
        self.fixture.put("notes.txt", "Unrelated change\n")
        self.fixture.base = self.fixture.commit()
        result = self.run_refresh()
        self.assertEqual(result["status"], "held")
        self.assertIn("no automatic rebase", result["reason"])
        self.no_push()

    def test_removals_version_auth_and_server_changes_are_held(self):
        original = copy.deepcopy(self.fixture.new)
        variants = []
        deleted = copy.deepcopy(original)
        deleted["paths"] = {}
        variants.append(deleted)
        version = copy.deepcopy(original)
        version["info"]["version"] = "2.1"
        variants.append(version)
        server = copy.deepcopy(original)
        server["servers"] = [{"url": "https://other.example.com"}]
        variants.append(server)
        auth = copy.deepcopy(original)
        auth["components"]["securitySchemes"] = {"Token": {"type": "http", "scheme": "bearer"}}
        auth["security"] = [{"Token": []}]
        variants.append(auth)
        schema = copy.deepcopy(original)
        schema["components"]["schemas"] = {}
        variants.append(schema)
        for spec in variants:
            with self.subTest(spec=spec["info"]["version"]):
                self.fixture.specs["example"] = spec
                self.assertEqual(self.run_refresh()["status"], "held")
                self.no_push()

    def test_edited_reviewed_or_ready_prs_are_never_updated(self):
        self.pending.pr["body"] += "\nHuman note"
        self.assertEqual(self.run_refresh()["status"], "held")
        self.no_push()
        self.pending.pr["body"] = draft_pr.pr_body(self.pending.old)
        self.pending.pr["draft"] = False
        self.assertEqual(self.run_refresh()["status"], "held")
        self.no_push()

    def test_changed_head_before_push_is_not_overwritten(self):
        original = self.pending.api
        calls = 0
        def api(endpoint, method="GET", payload=None):
            nonlocal calls
            response = original(endpoint, method, payload)
            if endpoint.endswith("/pulls/42"):
                calls += 1
                if calls == 3:
                    response["head"]["sha"] = "a" * 40
            return response
        self.pending.gh.side_effect = api
        with self.assertRaisesRegex(ValueError, "changed before push"):
            self.run_refresh()
        self.no_push()

    def test_concurrent_real_remote_commit_fails_lease_and_persists_guard(self):
        other = self.fixture.modified_commit(self.pending.head, "notes.txt", "Human commit\n")
        # The fixture's intentionally altered candidate is a sibling of the
        # generated head. Force it into the bare remote to model an external
        # writer; the updater must still use its own exact-head lease.
        self.fixture.git("push", "--force", "origin", other + ":refs/heads/" + self.pending.old["branch"])
        with self.assertRaises(draft_pr.PublicationFailure):
            self.run_refresh()
        guard = self.fixture.cache / "publication/example/blocked.json"
        self.assertEqual(json.loads(guard.read_text())["stage"], "push_pending_head")
        self.assertEqual(self.fixture.git("ls-remote", "origin", "refs/heads/" + self.pending.old["branch"]).split()[0], other)
        self.git_mock.reset_mock()
        with self.assertRaisesRegex(ValueError, "no retry"):
            self.run_refresh()
        self.no_push()

    def test_human_body_change_after_push_is_preserved_with_uncertain_outcome_guard(self):
        self.after_push = lambda: self.pending.pr.update(body="Human edited body")
        with self.assertRaises(draft_pr.PublicationFailure):
            self.run_refresh()
        self.assertEqual(self.pending.pr["body"], "Human edited body")
        blocked = self.fixture.cache / "publication/example/blocked.json"
        self.assertEqual(json.loads(blocked.read_text())["stage"], "verify_pending_update")

    def test_post_push_remote_main_advance_is_never_retried_or_hidden(self):
        calls = 0
        def guard(plan):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise ValueError("Main advanced")
        self.remote.side_effect = guard
        with self.assertRaises(draft_pr.PublicationFailure):
            self.run_refresh()
        self.assertTrue((self.fixture.cache / "publication/example/blocked.json").exists())

    def test_success_receipt_write_failure_persists_failed_outcome(self):
        original = Path.write_text
        def write(path, *args, **kwargs):
            if path.name == "result.json":
                raise OSError("Cannot save success receipt")
            return original(path, *args, **kwargs)
        with patch.object(Path, "write_text", write):
            with self.assertRaises(draft_pr.PublicationFailure):
                self.run_refresh()
        blocked = self.fixture.cache / "publication/example/blocked.json"
        self.assertEqual(json.loads(blocked.read_text())["stage"], "verify_pending_update")
        self.assertFalse((blocked.parent / "publishing.lock").exists())

    def test_unsavable_post_push_evidence_retains_interrupted_lock(self):
        self.after_push = lambda: self.pending.pr.update(body="Human edit")
        original = Path.write_text
        def write(path, *args, **kwargs):
            if path.name == "blocked.json":
                raise OSError("Full evidence disk")
            return original(path, *args, **kwargs)
        with patch.object(Path, "write_text", write):
            with self.assertRaisesRegex(OSError, "Full evidence disk"):
                self.run_refresh()
        self.assertTrue((self.fixture.cache / "publication/example/publishing.lock").exists())
        self.git_mock.reset_mock()
        with self.assertRaisesRegex(ValueError, "interrupted"):
            self.run_refresh()
        self.no_push()

    def test_publication_guard_and_interrupted_lock_are_not_removed(self):
        directory = self.fixture.cache / "publication/example"
        directory.mkdir(parents=True)
        blocked = directory / "blocked.json"
        blocked.symlink_to(directory / "missing")
        with self.assertRaisesRegex(ValueError, "no retry"):
            self.run_refresh()
        self.assertTrue(blocked.is_symlink())
        blocked.unlink()
        lock = directory / "publishing.lock"
        lock.write_text("Previous interrupted attempt\n")
        with self.assertRaisesRegex(ValueError, "interrupted"):
            self.run_refresh()
        self.assertEqual(lock.read_text(), "Previous interrupted attempt\n")
        self.no_push()

    def test_default_cli_is_fresh_read_only_review_and_saves_outcome(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = refresh_pr.main(["--source", "example", "--base", self.fixture.base,
                                      "--cache", str(self.fresh), "--prior-cache", str(self.fixture.cache)])
        result = json.loads(output.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(result["status"], "pending_refresh_requires_review")
        self.assertIs(result["publication_authorized"], False)
        self.no_push()
        self.assertEqual(json.loads((self.fresh / "refresh-result.json").read_text()), result)

    def test_unchanged_pending_head_is_not_replaced_for_fetch_date_changes(self):
        self.fixture.new["paths"]["/items/{id}"]["get"]["responses"]["200"]["description"] = "New response"
        self.assertEqual(self.run_refresh()["status"], "held")
        self.no_push()


if __name__ == "__main__":
    unittest.main()
