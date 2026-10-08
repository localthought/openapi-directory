import contextlib
import copy
import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import draft_pr
import pending_pr
import test_draft_pr
import update


class PendingTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_draft_pr.DraftTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.old = self.fixture.plan()
        self.head = draft_pr.commit_plan(self.old)
        self.pr = {"number": 42, "html_url": "https://github.com/ontola/openapi-directory/pull/42",
                   "state": "open", "draft": True,
                   "head": {"sha": self.head, "ref": self.old["branch"], "repo": {"full_name": draft_pr.REPOSITORY}},
                   "base": {"sha": self.fixture.base, "ref": "main", "repo": {"full_name": draft_pr.REPOSITORY}},
                   "title": "Update official example API", "body": draft_pr.pr_body(self.old),
                   "updated_at": "2026-10-06T12:01:00Z", "changed_files": len(self.old["files"]),
                   "comments": 0, "review_comments": 0, "requested_reviewers": [], "requested_teams": []}
        self.matches = [{"number": 42, "url": self.pr["html_url"], "head": self.head}]
        self.files = [{"filename": p} for p in self.old["files"]]
        self.reviews = []
        self.receipt()
        self.gh_patch = patch.object(draft_pr, "gh_json", side_effect=self.api)
        self.gh = self.gh_patch.start()
        self.addCleanup(self.gh_patch.stop)
        self.pending_patch = patch.object(draft_pr, "existing_pr", side_effect=lambda plan: self.matches)
        self.pending = self.pending_patch.start()
        self.addCleanup(self.pending_patch.stop)

    def receipt(self):
        self.directory = self.fixture.cache / self.old["group"] / self.old["seal"]
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / "candidate.json").write_text(json.dumps(self.old) + "\n")
        self.result = {"status": "draft_created", "group": self.old["group"],
                       "candidate_sha256": self.old["seal"], "files": sorted(self.old["files"]),
                       "head": self.pr["head"]["sha"], "base_revision": self.old["base_revision"],
                       "number": 42, "url": self.pr["html_url"]}
        (self.directory / "result.json").write_text(json.dumps(self.result) + "\n")

    def api(self, endpoint, method="GET", payload=None):
        self.assertEqual(method, "GET")
        self.assertIsNone(payload)
        if "/reviews?" in endpoint:
            return copy.deepcopy(self.reviews)
        if "/files?" in endpoint:
            return copy.deepcopy(self.files)
        if endpoint.endswith("/pulls/42"):
            return copy.deepcopy(self.pr)
        self.fail("Unexpected endpoint " + endpoint)

    def review(self):
        return pending_pr.review(self.fixture.plan(), self.fixture.cache)

    def held(self, reason):
        result = self.review()
        self.assertEqual(result["status"], "held")
        self.assertIn(reason, result["reason"])
        self.assertIs(result["read_only"], True)
        self.assertIs(result["publication_authorized"], False)

    def use_generation(self, generation, receipt_branch=None):
        plan = self.fixture.plan()
        self.old = draft_pr.with_branch(plan, draft_pr.branch_name(plan["group"], generation))
        self.head = draft_pr.commit_plan(self.old)
        self.pr["head"] = {"sha": self.head, "ref": self.old["branch"], "repo": {"full_name": draft_pr.REPOSITORY}}
        self.pr["body"] = draft_pr.pr_body(self.old)
        self.matches = [{"number": 42, "url": self.pr["html_url"], "head": self.head}]
        if receipt_branch is not None:
            # Retained evidence claims a different generation than the actual PR.
            self.old = draft_pr.with_branch(self.old, receipt_branch)
        self.receipt()

    def test_later_generation_draft_is_reviewed_with_its_own_receipt(self):
        self.use_generation(2)
        result = self.review()
        self.assertEqual(result["status"], "pending_matches_source")
        self.assertEqual(result["branch"], "codex/official-update-example--g2")
        self.assertEqual(result["head"], self.head)
        self.assertIs(result["publication_authorized"], False)

    def test_later_generation_with_another_generations_receipt_is_held(self):
        self.use_generation(2, receipt_branch="codex/official-update-example")
        self.held("PR identity differs")

    def test_exact_pending_vendor_match_ignores_fetch_timestamp_only_changes(self):
        original_fetch = self.fixture.fetch
        def fetch(source):
            raw, meta = original_fetch(source)
            meta["fetched_at"] = "2026-10-06T15:00:00Z"
            return raw, meta
        self.fixture.fetch_mock.side_effect = fetch
        result = self.review()
        self.assertEqual(result["status"], "pending_matches_source")
        self.assertEqual(result["head"], self.head)
        self.assertEqual(result["comparisons_from_pending"][0]["status"], "matches_source")
        self.assertIs(result["publication_authorized"], False)

    def test_changed_source_is_compared_to_pending_instead_of_main_and_requires_review(self):
        self.fixture.new["paths"]["/items/{id}"]["get"]["responses"]["200"]["description"] = "Another response"
        self.fixture.new["paths"]["/new"] = {"get": {"responses": {"200": {"description": "New endpoint"}}}}
        result = self.review()
        self.assertEqual(result["status"], "pending_refresh_requires_review")
        comparison = result["comparisons_from_pending"][0]
        self.assertEqual(comparison["stored"]["version"], "2.0")
        self.assertEqual(comparison["added_operations"], ["GET /new"])
        self.assertIs(result["publication_authorized"], False)

    def test_removed_operation_is_reported_without_update_permission(self):
        self.fixture.new["paths"] = {}
        result = self.review()
        self.assertEqual(result["status"], "pending_refresh_requires_review")
        self.assertEqual(result["comparisons_from_pending"][0]["removed_operations"], ["GET /items/{id}"])
        self.assertIs(result["publication_authorized"], False)

    def test_no_pending_pr_is_not_permission_to_publish(self):
        self.matches = []
        result = self.review()
        self.assertEqual(result["status"], "no_pending_pr")
        self.assertEqual(result["source_status"], "candidate")
        self.gh.assert_not_called()
        self.assertIs(result["publication_authorized"], False)

    def test_multiple_overlapping_prs_hold_every_branch(self):
        self.matches.append({"number": 43, "url": "https://github.com/ontola/openapi-directory/pull/43", "head": "b" * 40})
        self.held("Multiple overlapping")
        self.gh.assert_not_called()

    def test_failure_and_interruption_guards_are_retained_before_remote_reads(self):
        directory = self.fixture.cache / "publication/example"
        directory.mkdir(parents=True)
        for name in ["blocked.json", "publishing.lock"]:
            with self.subTest(name=name):
                p = directory / name
                p.write_text("prior uncertain outcome\n")
                self.held("Retained failed/uncertain")
                self.pending.assert_not_called()
                self.gh.assert_not_called()
                self.assertEqual(p.read_text(), "prior uncertain outcome\n")
                p.unlink()
        (directory / "blocked.json").symlink_to(directory / "missing")
        self.held("Retained failed/uncertain")

    def test_ready_closed_foreign_or_manual_prs_are_held(self):
        original = copy.deepcopy(self.pr)
        changes = [("draft", False), ("state", "closed"), ("html_url", "https://example.com/pr")]
        for field, value in changes:
            self.pr = copy.deepcopy(original)
            self.pr[field] = value
            self.held("not an open generated draft")
        for side, field, value in [("head", "ref", "human-branch"), ("base", "ref", "other"),
                                    ("head", "repo", {"full_name": "other/repo"}),
                                    ("base", "repo", {"full_name": "other/repo"}),
                                    ("base", "sha", "not-a-sha")]:
            self.pr = copy.deepcopy(original)
            self.pr[side][field] = value
            self.held("not an open generated draft")

    def test_discussion_requested_or_submitted_reviews_hold_the_existing_work(self):
        for field, value in [("comments", 1), ("review_comments", 1),
                             ("requested_reviewers", [{"login": "reviewer"}]),
                             ("requested_teams", [{"slug": "reviewers"}])]:
            with self.subTest(field=field):
                self.pr[field] = value
                self.held("discussion or review requests")
                self.pr[field] = [] if isinstance(value, list) else 0
        self.reviews = [{"state": "APPROVED", "body": ""}]
        self.held("submitted reviews")

    def test_edited_body_or_title_is_not_overwritten(self):
        original = copy.deepcopy(self.pr)
        for field in ["body", "title"]:
            self.pr = copy.deepcopy(original)
            self.pr[field] += "\nHuman review note"
            self.held("title/body has been edited")

    def test_missing_or_unknown_publication_receipt_is_not_a_generated_branch_assumption(self):
        (self.directory / "result.json").unlink()
        self.held("Exactly one retained")
        self.receipt()
        self.result["status"] = "failed"
        (self.directory / "result.json").write_text(json.dumps(self.result))
        self.held("Exactly one retained")

    def test_edited_receipt_and_candidate_fail_integrity_checks(self):
        self.result["files"] = ["README.md"]
        (self.directory / "result.json").write_text(json.dumps(self.result))
        self.held("integrity changed")
        self.receipt()
        altered = copy.deepcopy(self.old)
        altered["files"]["README.md"] = "Unrelated"
        (self.directory / "candidate.json").write_text(json.dumps(altered))
        self.held("integrity changed")

    def test_symlink_or_duplicate_json_evidence_is_not_trusted(self):
        path = self.directory / "candidate.json"
        raw = path.read_text()
        path.unlink()
        elsewhere = self.directory / "elsewhere.json"
        elsewhere.write_text(raw)
        path.symlink_to(elsewhere)
        self.held("redirected retained")
        path.unlink()
        path.write_text('{"seal":"one","seal":"two"}')
        self.held("Duplicate key")

    def test_extra_remote_file_or_truncated_file_listing_is_held(self):
        self.files.append({"filename": "README.md"})
        self.held("file scope differs")
        self.files = self.files[:1]
        self.held("file scope differs")

    def test_human_commit_with_same_candidate_trailer_cannot_forge_exact_tree(self):
        altered = self.fixture.modified_commit(self.head, "README.md", "User change\n")
        tree = self.fixture.git("rev-parse", altered + "^{tree}")
        message = "Update official example API description\n\nCandidate SHA-256: " + self.old["seal"] + "\n"
        forged = draft_pr.git("commit-tree", tree, "-p", self.fixture.base, data=message.encode()).decode().strip()
        self.pr["head"]["sha"] = forged
        self.matches[0]["head"] = forged
        self.receipt()
        self.held("file scope differs")

    def test_main_unrelated_advance_is_observed_without_rebase_or_checkout_changes(self):
        self.fixture.put("notes.txt", "Unrelated main update\n")
        self.fixture.base = self.fixture.commit()
        self.fixture.put("staged.txt", "User's staged work\n")
        self.fixture.git("add", "staged.txt")
        before = (self.fixture.git("status", "--porcelain"), self.fixture.git("diff", "--cached"), self.fixture.git("rev-parse", "HEAD"))
        result = self.review()
        self.assertEqual(result["status"], "pending_matches_source")
        self.assertEqual(result["intervening_main_changes"], ["notes.txt"])
        self.assertEqual(before, (self.fixture.git("status", "--porcelain"), self.fixture.git("diff", "--cached"), self.fixture.git("rev-parse", "HEAD")))

    def test_main_api_or_manifest_advance_requires_deliberate_reconciliation(self):
        self.fixture.put(self.fixture.sources[0]["target"], update.serialize_document(self.fixture.old) + "\n")
        self.fixture.base = self.fixture.commit()
        self.held("Main changed this API")
        self.fixture.sources[0]["url"] = "https://example.com/new-reviewed-source.json"
        self.fixture.save_manifest()
        self.fixture.base = self.fixture.commit()
        self.held("Source group/recipe changed")

    def test_pr_change_during_pagination_and_lost_head_fail_closed(self):
        calls = 0
        original = self.api
        def changed(endpoint, method="GET", payload=None):
            nonlocal calls
            response = original(endpoint, method, payload)
            if endpoint.endswith("/pulls/42"):
                calls += 1
                if calls == 2:
                    response["updated_at"] = "2026-10-06T16:00:00Z"
            return response
        self.gh.side_effect = changed
        self.held("changed during verification")
        self.gh.side_effect = original
        self.pr["head"]["sha"] = "a" * 40
        self.held("identity changed during discovery")

    def test_cli_saves_fresh_candidate_and_read_only_review_without_git_or_rest_mutations(self):
        output = io.StringIO()
        original_git = draft_pr.git
        forbidden = {"push", "commit-tree", "update-ref", "checkout", "switch", "read-tree", "update-index"}
        def git(*args, **kwargs):
            self.assertNotIn(args[0], forbidden)
            return original_git(*args, **kwargs)
        cache = self.fixture.cache / "fresh-review"
        with patch.object(draft_pr, "git", side_effect=git), contextlib.redirect_stdout(output):
            status = pending_pr.main(["--source", "example", "--base", self.fixture.base,
                                      "--cache", str(cache), "--prior-cache", str(self.fixture.cache)])
        self.assertEqual(status, 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "pending_matches_source")
        self.assertEqual(json.loads((cache / "pending-review.json").read_text()), result)
        self.assertTrue((cache / "latest-result.json").exists())

    def test_missing_git_objects_and_nonancestor_advertised_base_are_held(self):
        self.pr["base"]["sha"] = "a" * 40
        self.held("Git objects or ancestry")
        self.pr["base"]["sha"] = self.head
        self.held("Git objects or ancestry")

    def test_same_cache_root_is_rejected_before_overwriting_creation_evidence(self):
        original = (self.directory / "result.json").read_bytes()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            pending_pr.main(["--source", "example", "--cache", str(self.fixture.cache),
                             "--prior-cache", str(self.fixture.cache / "alias" / "..")])
        self.assertEqual(error.exception.code, 2)
        self.assertEqual((self.directory / "result.json").read_bytes(), original)
        self.pending.assert_not_called()
        self.gh.assert_not_called()

    def test_invalid_fresh_vendor_document_cannot_be_reported_as_pending_match(self):
        self.fixture.new["paths"]["/items/{id}"]["get"]["responses"] = {}
        cache = self.fixture.cache / "invalid-fresh-review"
        with contextlib.redirect_stdout(io.StringIO()):
            status = pending_pr.main(["--source", "example", "--base", self.fixture.base,
                                      "--cache", str(cache), "--prior-cache", str(self.fixture.cache)])
        self.assertEqual(status, 1)
        result = json.loads((cache / "pending-review.json").read_text())
        self.assertEqual(result["status"], "failed")
        self.assertIs(result["publication_authorized"], False)
        self.assertNotIn("comparisons_from_pending", result)
        self.assertTrue((cache / "failure.json").exists())
        self.pending.assert_not_called()
        self.gh.assert_not_called()

    def test_current_main_matching_a_reverted_source_does_not_close_the_pending_pr(self):
        self.fixture.specs["example"] = test_draft_pr.document()
        result = self.review()
        self.assertEqual(result["status"], "pending_superseded_by_main_requires_review")
        self.assertEqual(result["comparisons_from_pending"][0]["stored"]["version"], "2.0")
        self.assertEqual(result["comparisons_from_pending"][0]["source"]["version"], "1.0")
        self.assertIs(result["publication_authorized"], False)

    def test_companion_artifacts_are_verified_and_compared_as_one_explicit_group(self):
        f = self.fixture
        f.sources[0]["publication_group"] = "example-public"
        f.sources.append({**copy.deepcopy(f.sources[0]), "id": "example-dated",
                          "target": "APIs/example.com/dated/1.0/openapi.yaml"})
        f.specs["example-dated"] = test_draft_pr.document("2.0")
        f.save_manifest()
        f.base = f.commit()
        self.old = f.plan()
        self.head = draft_pr.commit_plan(self.old)
        self.pr["head"].update(sha=self.head, ref=self.old["branch"])
        self.pr["base"]["sha"] = f.base
        self.pr.update(title="Update official example-public API", body=draft_pr.pr_body(self.old),
                       changed_files=len(self.old["files"]))
        self.matches[0]["head"] = self.head
        self.files = [{"filename": p} for p in self.old["files"]]
        self.receipt()
        f.specs["example-dated"]["paths"]["/items/{id}"]["get"]["responses"]["200"]["description"] = "Dated change"
        result = self.review()
        self.assertEqual(result["status"], "pending_refresh_requires_review")
        self.assertEqual([c["status"] for c in result["comparisons_from_pending"]], ["matches_source", "changed"])
        self.assertEqual(result["group"], "example-public")
        self.assertIs(result["publication_authorized"], False)


if __name__ == "__main__":
    unittest.main()
