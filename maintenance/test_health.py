import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import health
import report
import update
from test_update import document


SOURCE = {"id": "test", "target": "APIs/example.com/1.0/openapi.yaml",
          "provider": "example.com", "version_policy": "vendor",
          "github": {"repository": "Vendor/specs", "ref": "main", "path": "api.json"}}


def repository(**changes):
    return {"full_name": "Vendor/specs", "owner": {"login": "Vendor"},
            "archived": False, "disabled": False, "private": False, "fork": False,
            "default_branch": "main", "pushed_at": "2026-10-02T14:00:00Z",
            "updated_at": "2026-10-02T14:00:00Z", **changes}


class HealthTests(unittest.TestCase):
    def test_shared_repository_fetches_once_and_caches_exact_evidence(self):
        raw = json.dumps(repository()).encode()
        request = Mock(return_value=(raw, {"url": "https://api.github.com/repos/Vendor/specs", "etag": "etag"}))
        with tempfile.TemporaryDirectory() as directory:
            checker = health.Checker(request, lambda: "today", Path(directory))
            result = checker.check(SOURCE)
            second = copy.deepcopy(SOURCE)
            second["github"]["repository"] = "vendor/SPECS"
            result["source_health_check"]["owner"] = "caller mutation"
            repeated = checker.check(second)
            request.assert_called_once_with("https://api.github.com/repos/Vendor/specs")
            self.assertEqual(repeated["source_health"], "repository_available")
            self.assertEqual(repeated["source_health_check"]["owner"], "Vendor")
            self.assertEqual(repeated["last_successful_source_health_check"], "today")
            snapshot = Path(directory) / repeated["source_health_check"]["snapshot"]
            self.assertEqual((snapshot / "repository.json").read_bytes(), raw)
            self.assertEqual(json.loads((snapshot / "fetch.json").read_text())["sha256"], update.sha256(raw))
            self.assertIn("still require review", repeated["source_health_check"]["scope"])

    def test_archived_disabled_and_redirects_block_even_with_recent_activity(self):
        for data, state in ((repository(archived=True), "archived"),
                            (repository(disabled=True), "disabled"),
                            (repository(full_name="Other/specs", owner={"login": "Other"}), "identity_changed")):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as directory:
                checker = health.Checker(Mock(return_value=(json.dumps(data).encode(), {})), lambda: "today", Path(directory))
                result = checker.check(SOURCE)
                self.assertEqual(result["source_health"], state)
                self.assertTrue(result["source_health_issue"])
                self.assertEqual(result["last_successful_source_health_check"], "today")
                self.assertEqual(report.state({"status": "matches_source", **result}), "Import blocked")

    def test_malformed_metadata_fails_without_advancing_health_success(self):
        for data in ({}, [], repository(archived="false"), repository(private=True),
                     repository(owner={"login": "Other"}), repository(default_branch=None)):
            with self.subTest(data=data), tempfile.TemporaryDirectory() as directory:
                result = health.Checker(Mock(return_value=(json.dumps(data).encode(), {})), lambda: "today", Path(directory)).check(SOURCE)
                self.assertEqual(result["source_health"], "check_failed")
                self.assertNotIn("last_successful_source_health_check", result)
                self.assertEqual(result["source_health_check"]["status"], "failed")
                self.assertIn("sha256", result["source_health_check"])

    def test_failed_metadata_fetch_is_deduplicated_but_not_reused_next_run(self):
        request = Mock(side_effect=OSError("Network unavailable"))
        with tempfile.TemporaryDirectory() as directory:
            checker = health.Checker(request, lambda: "today", Path(directory))
            first = checker.check(SOURCE)
            checker.check(SOURCE)
            request.assert_called_once()
            health.Checker(request, lambda: "tomorrow", Path(directory)).check(SOURCE)
            self.assertEqual(request.call_count, 2)
            self.assertNotIn("last_successful_source_health_check", first)

    def test_hosted_sources_are_explicitly_unassessed_and_unsafe_repos_never_fetch(self):
        request = Mock()
        with tempfile.TemporaryDirectory() as directory:
            checker = health.Checker(request, lambda: "today", Path(directory))
            self.assertEqual(checker.check({"url": "https://vendor.example/api.json"})["source_health"], "not_assessed")
            for name in ("../specs", "Vendor/..", "Vendor/specs?query", "Vendor/a/b"):
                self.assertEqual(checker.check({"github": {"repository": name}})["source_health"], "check_failed")
            request.assert_not_called()

    def test_health_failure_keeps_independent_content_comparison_and_success_dates(self):
        raw = json.dumps(document()).encode()
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            path = cache / "report.json"
            path.write_text(json.dumps({"sources": [{"id": "test", "last_successful_source_health_check": "yesterday"}]}))
            with patch.object(update, "request", side_effect=OSError("Metadata unavailable")), \
                 patch.object(update, "fetch", return_value=(raw, {"sha256": update.sha256(raw), "fetched_at": "today"})), \
                 patch.object(update, "stored", return_value=document()), \
                 patch.object(update, "git", return_value=b"base\n"):
                result = update.audit(SOURCE, "origin/main", cache)
                update.write_report(path, [result], "origin/main")
            self.assertEqual(result["status"], "matches_source")
            self.assertEqual(result["validation_errors"], [])
            self.assertEqual(result["last_successful_fetch"], "today")
            self.assertEqual(result["last_successful_source_health_check"], "yesterday")
            self.assertEqual(report.state(result), "Import blocked")
            readable = path.with_suffix(".md").read_text()
            self.assertIn("Metadata unavailable", readable)
            self.assertIn("yesterday", readable)

    def test_import_refuses_archive_or_failed_health_before_artifact_fetch(self):
        for request in (Mock(side_effect=OSError("Metadata unavailable")),
                        Mock(return_value=(json.dumps(repository(archived=True)).encode(), {}))):
            with tempfile.TemporaryDirectory() as directory, \
                 patch.object(update, "load_sources", return_value=[SOURCE]), \
                 patch.object(update, "request", request), patch.object(update, "fetch") as fetch:
                with self.assertRaisesRegex(ValueError, "archived|health check failed"):
                    update.main(["import", "--source", "test", "--cache", directory])
                fetch.assert_not_called()

    def test_check_exit_status_includes_health_failures_even_with_valid_match(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(update, "load_sources", return_value=[SOURCE]), \
             patch.object(update, "audit", return_value={"id": "test", "status": "matches_source",
                                                       "source_health_issue": "Unavailable"}), \
             patch.object(update, "write_report"):
            self.assertEqual(update.main(["check", "--cache", directory]), 1)


if __name__ == "__main__":
    unittest.main()
