import contextlib
import copy
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import draft_pr
import update
from test_update import document


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "checkout"
        self.root.mkdir()
        for path in draft_pr.REQUIRED_INPUTS:
            self.put(path, (update.ROOT / path).read_text())
        self.root_patch = patch.object(update, "ROOT", self.root)
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.com")
        self.sources = [{"id": "example", "provider": "example.com",
                         "target": "APIs/example.com/1.0/openapi.yaml",
                         "url": "https://example.com/openapi.json", "version_policy": "vendor"}]
        self.old = document()
        self.old["info"]["x-logo"] = {"url": "https://example.com/logo.svg"}
        self.old["tags"] = [{"name": "curated", "description": "Retain me"}]
        self.put(self.sources[0]["target"], update.serialize_document(self.old))
        self.put("APIs/other.com/old/swagger.yaml", "unrelated historical file\n")
        self.put("maintenance/recipe.py", "# committed input\n")
        self.save_manifest()
        self.base = self.commit()
        self.cache = Path(self.temporary.name) / "cache"
        self.new = document("2.0")
        self.new["paths"]["/items/{id}"]["get"]["responses"]["200"]["description"] = "New response"
        self.specs = {"example": self.new}
        self.fetch_patch = patch.object(update, "fetch", side_effect=self.fetch)
        self.fetch_mock = self.fetch_patch.start()
        self.addCleanup(self.fetch_patch.stop)
        self.health_patch = patch.object(draft_pr.health, "Checker")
        self.checker = self.health_patch.start()
        self.addCleanup(self.health_patch.stop)
        self.checker.return_value.check.return_value = {"source_health": "not_assessed"}

    def git(self, *args, data=None):
        return subprocess.check_output(["git", *args], cwd=self.root, input=data, stderr=subprocess.PIPE).decode().strip()

    def put(self, path, content):
        destination = self.root / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content)

    def save_manifest(self):
        self.put(draft_pr.MANIFEST, json.dumps({"schema_version": 1, "sources": self.sources}, indent=2) + "\n")

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-m", "fixture")
        return self.git("rev-parse", "HEAD")

    def fetch(self, source):
        raw = json.dumps(self.specs[source["id"]]).encode()
        return raw, {"sha256": update.sha256(raw), "url": source["url"],
                     "revision": None, "fetched_at": "2026-10-06T12:00:00Z"}

    def plan(self):
        return draft_pr.build_plan("example", self.base, self.cache)

    def remote(self):
        self.bare = Path(self.temporary.name) / "remote.git"
        subprocess.check_output(["git", "init", "--bare", str(self.bare)], stderr=subprocess.PIPE)
        self.git("remote", "add", "origin", str(self.bare))
        self.git("push", "origin", "HEAD:refs/heads/main")

    def fake_github(self, plan, bad_head=False):
        def respond(endpoint, method="GET", payload=None):
            if method == "POST" or endpoint.endswith("/pulls/42"):
                if method == "POST":
                    self.assertIs(payload["draft"], True)
                    self.assertEqual(payload["base"], "main")
                    self.assertEqual(payload["head"], plan["branch"])
                head = self.git("ls-remote", "origin", "refs/heads/" + plan["branch"]).split()[0]
                return {"number": 42, "html_url": "https://github.com/ontola/openapi-directory/pull/42",
                        "draft": True, "state": "open",
                        "head": {"ref": plan["branch"], "sha": "0" * 40 if bad_head else head,
                                 "repo": {"full_name": draft_pr.REPOSITORY}},
                        "base": {"ref": "main", "sha": self.base, "repo": {"full_name": draft_pr.REPOSITORY}}}
            if "/pulls/42/files" in endpoint:
                return [{"filename": path} for path in plan["files"]]
            return []
        return respond

    def test_version_import_full_sparse_tree_and_dirty_index_are_preserved(self):
        self.git("sparse-checkout", "init", "--cone")
        self.git("sparse-checkout", "set", "maintenance")
        self.assertFalse((self.root / self.sources[0]["target"]).exists())
        self.put("notes.txt", "staged user change\n")
        self.git("add", "notes.txt")
        before = (self.git("status", "--porcelain"), self.git("diff", "--cached"), self.git("rev-parse", "HEAD"))
        plan = self.plan()
        self.assertEqual(set(plan["files"]), {"APIs/example.com/2.0/openapi.yaml", draft_pr.MANIFEST})
        parsed = update.parse(plan["files"]["APIs/example.com/2.0/openapi.yaml"].encode())
        self.assertEqual(parsed["info"]["x-logo"], self.old["info"]["x-logo"])
        self.assertEqual(parsed["tags"], self.old["tags"])
        self.assertEqual(update.compare(parsed, self.new)["status"], "matches_source")
        commit = draft_pr.commit_plan(plan)
        self.assertEqual(self.git("rev-parse", commit + "^"), self.base)
        self.assertEqual(self.git("diff", "--name-only", self.base, commit).splitlines(), sorted(plan["files"]))
        self.assertEqual(self.git("show", commit + ":APIs/other.com/old/swagger.yaml"), "unrelated historical file")
        self.assertEqual(self.git("show", commit + ":" + self.sources[0]["target"]), self.git("show", self.base + ":" + self.sources[0]["target"]))
        self.assertEqual(before, (self.git("status", "--porcelain"), self.git("diff", "--cached"), self.git("rev-parse", "HEAD")))
        raw, metadata = self.fetch(self.sources[0])
        self.assertEqual((self.cache / "example" / metadata["sha256"] / "source").read_bytes(), raw)
        manifest = json.loads(plan["files"][draft_pr.MANIFEST])
        expected = copy.deepcopy(self.sources)
        expected[0]["target"] = "APIs/example.com/2.0/openapi.yaml"
        self.assertEqual(manifest["sources"], expected)

    def test_fixed_version_drift_changes_only_api(self):
        self.new["info"]["version"] = "1.0"
        plan = self.plan()
        self.assertEqual(set(plan["files"]), {self.sources[0]["target"]})
        self.assertEqual(plan["sources"][0]["comparison"]["status"], "changed")
        draft_pr.commit_plan(plan)

    def test_current_vendor_content_never_writes_timestamp_only_pr(self):
        self.specs["example"] = document()
        plan = self.plan()
        self.assertEqual(plan["status"], "matches_source")
        self.assertEqual(plan["files"], {})

    def test_missing_api_reports_all_additions(self):
        self.git("rm", self.sources[0]["target"])
        self.base = self.commit()
        plan = self.plan()
        comparison = plan["sources"][0]["comparison"]
        self.assertEqual(comparison["added_paths"], ["/items/{id}"])
        self.assertEqual(comparison["added_operations"], ["GET /items/{id}"])
        self.assertIn("added paths: 1", draft_pr.pr_body(plan))

    def test_explicit_companion_group_is_one_commit_and_block_is_all_or_nothing(self):
        self.sources[0]["publication_group"] = "example-public"
        second = {**self.sources[0], "id": "example-dated", "target": "APIs/example.com/dated/1.0/openapi.yaml"}
        self.sources.append(second)
        self.specs[second["id"]] = document("2.1")
        self.save_manifest()
        self.base = self.commit()
        plan = self.plan()
        self.assertEqual(plan["branch"], "codex/official-update-example-public")
        self.assertEqual([s["id"] for s in plan["sources"]], [s["id"] for s in self.sources])
        self.assertEqual(len(plan["files"]), 3)
        draft_pr.commit_plan(plan)
        second["import_blocker"] = "Owner choice pending; do not retry"
        self.save_manifest()
        self.base = self.commit()
        self.fetch_mock.reset_mock()
        self.checker.reset_mock()
        with self.assertRaisesRegex(ValueError, "Owner choice"):
            self.plan()
        self.fetch_mock.assert_not_called()
        self.checker.assert_not_called()

    def test_bad_native_schema_and_adverse_health_stop_before_git_commit(self):
        self.new["components"]["schemas"]["Choice"]["oneOf"] = []
        with self.assertRaisesRegex(ValueError, "validation failed"):
            self.plan()
        self.assertEqual(self.git("rev-parse", "HEAD"), self.base)
        self.checker.return_value.check.return_value = {"source_health_issue": "archived repository"}
        self.fetch_mock.reset_mock()
        with self.assertRaisesRegex(ValueError, "archived"):
            self.plan()
        self.fetch_mock.assert_not_called()

    def test_companion_github_sources_pin_the_same_commit_even_if_main_advances(self):
        self.sources[0].update(publication_group="example-public", github={
            "repository": "example/spec", "ref": "main", "path": "default.json"})
        self.sources.append({**copy.deepcopy(self.sources[0]), "id": "example-dated",
                             "target": "APIs/example.com/dated/1.0/openapi.yaml"})
        self.sources[1]["github"]["path"] = "dated.json"
        self.specs["example-dated"] = document("2.0")
        self.save_manifest()
        self.base = self.commit()
        def fetch(source):
            raw, metadata = self.fetch(source)
            metadata["revision"] = "a" * 40
            return raw, metadata
        self.fetch_mock.side_effect = fetch
        plan = self.plan()
        self.assertEqual(self.fetch_mock.call_args_list[-1].args[0]["github"]["ref"], "a" * 40)
        self.assertEqual([s["configuration"]["github"]["ref"] for s in plan["sources"]], ["main", "main"])
        self.assertEqual({s["fetch"]["revision"] for s in plan["sources"]}, {"a" * 40})
        calls = 0
        def inconsistent(source):
            nonlocal calls
            calls += 1
            raw, metadata = self.fetch(source)
            metadata["revision"] = ("a" if calls == 1 else "b") * 40
            return raw, metadata
        self.fetch_mock.side_effect = inconsistent
        with self.assertRaisesRegex(ValueError, "differs from pinned group"):
            self.plan()

    def test_changed_recipe_or_symlink_input_requires_rebuild(self):
        plan = self.plan()
        recipe = self.root / "maintenance/recipe.py"
        recipe.write_text("# changed\n")
        with self.assertRaisesRegex(ValueError, "maintenance input differs"):
            draft_pr.commit_plan(plan)

        recipe.unlink()
        target = self.root / "recipe-copy.txt"
        target.write_text("# committed input\n")
        recipe.symlink_to(target)
        with self.assertRaisesRegex(ValueError, "maintenance input differs"):
            draft_pr.commit_plan(plan)

    def test_converter_entrypoint_is_a_guarded_delivered_input(self):
        plan = self.plan()
        converter = self.root / "maintenance/convert-swagger.cjs"
        original = converter.read_bytes()
        converter.write_text("// changed converter options\n")
        with self.assertRaisesRegex(ValueError, "maintenance input differs"):
            draft_pr.commit_plan(plan)
        converter.write_bytes(original)
        draft_pr.verify_plan(plan)

    def test_comparison_tree_requires_delivered_tool_modules(self):
        self.git("rm", "maintenance/draft_pr.py")
        self.base = self.commit()
        with self.assertRaisesRegex(ValueError, "missing required maintenance inputs"):
            self.plan()

    def test_tampered_candidate_and_unrelated_manifest_change_are_rejected(self):
        plan = self.plan()
        plan["files"]["README.md"] = "unexpected"
        with self.assertRaisesRegex(ValueError, "integrity changed"):
            draft_pr.commit_plan(plan)
        plan["seal"] = draft_pr.seal(plan)
        with self.assertRaisesRegex(ValueError, "unexpected files"):
            draft_pr.commit_plan(plan)
        plan = self.plan()
        manifest = json.loads(plan["files"][draft_pr.MANIFEST])
        manifest["sources"][0]["url"] = "https://elsewhere.example/spec"
        plan["files"][draft_pr.MANIFEST] = json.dumps(manifest)
        plan["seal"] = draft_pr.seal(plan)
        with self.assertRaisesRegex(ValueError, "unrelated configuration"):
            draft_pr.commit_plan(plan)

    def test_resealed_outside_destination_or_changed_group_cannot_publish(self):
        for change in ("path", "branch", "group", "config"):
            plan = self.plan()
            if change == "path":
                row = plan["sources"][0]
                content = plan["files"].pop(row["destination"])
                row["destination"] = "APIs/other.com/2.0/openapi.yaml"
                plan["files"][row["destination"]] = content
            elif change == "config":
                plan["sources"][0]["configuration"]["url"] = "https://elsewhere.example/spec"
            else:
                plan[change] += "-changed"
            plan["seal"] = draft_pr.seal(plan)
            with self.subTest(change=change), self.assertRaises(ValueError):
                draft_pr.commit_plan(plan)

    def test_symlink_destination_ancestor_is_not_replaced(self):
        self.git("rm", "-r", "APIs/example.com")
        (self.root / "APIs/example.com").symlink_to("other.com", target_is_directory=True)
        self.base = self.commit()
        plan = self.plan()
        with self.assertRaisesRegex(ValueError, "regular Git"):
            draft_pr.commit_plan(plan)

    def test_default_cli_is_dry_run_with_immutable_candidate_and_no_github(self):
        with patch.object(draft_pr, "publish") as publish, patch.object(draft_pr, "gh_json") as gh, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(draft_pr.main(["--source", "example", "--base", self.base, "--cache", str(self.cache)]), 0)
        publish.assert_not_called()
        gh.assert_not_called()
        result = json.loads((self.cache / "latest-result.json").read_text())
        candidate = self.cache / "example" / result["candidate_sha256"]
        self.assertTrue((candidate / "body.md").exists())
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_cli_failure_has_safe_diagnostics_and_preserves_sources(self):
        self.new["components"]["schemas"]["Choice"]["oneOf"] = []
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(draft_pr.main(["--source", "example", "--base", self.base, "--cache", str(self.cache)]), 1)
        result = json.loads(output.getvalue())
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("diagnostic", result)
        self.assertIn("validation failed", json.loads((self.cache / "failure.json").read_text())["diagnostic"])
        self.assertTrue(list(self.cache.glob("example/*/source")))

    def test_open_pr_on_historical_version_is_held_without_push_or_comment(self):
        plan = self.plan()
        def respond(endpoint, method="GET", payload=None):
            self.assertEqual(method, "GET")
            if "/files" in endpoint:
                return [{"filename": self.sources[0]["target"]}]
            return [{"number": 9, "html_url": "https://github.com/ontola/openapi-directory/pull/9",
                     "head": {"ref": "someone-else", "sha": "a" * 40}}]
        with patch.object(draft_pr, "remote_guard"), patch.object(draft_pr, "gh_json", side_effect=respond), patch.object(draft_pr, "commit_plan") as commit:
            self.assertEqual(draft_pr.publish(plan, self.cache)["status"], "existing_pending")
        commit.assert_not_called()

    def test_pagination_reads_later_matches_and_fails_closed_at_bound(self):
        first = [{"filename": "unrelated/" + str(i)} for i in range(100)]
        with patch.object(draft_pr, "gh_json", side_effect=[first, [{"filename": self.sources[0]["target"]}]]) as gh:
            self.assertEqual(draft_pr.pages("files")[-1]["filename"], self.sources[0]["target"])
            self.assertIn("page=2", gh.call_args.args[0])
        with patch.object(draft_pr, "gh_json", return_value=first), self.assertRaisesRegex(ValueError, "pagination exceeds"):
            draft_pr.pages("files", limit=2)

    def test_origin_identity_and_advancing_main_fail_closed(self):
        plan = self.plan()
        for remote in ("https://github.com/ontola/openapi-directory.git", "git@github.com:localthought/openapi-directory.git"):
            with patch.object(draft_pr, "git", side_effect=[remote.encode(), remote.encode(), (self.base + "\trefs/heads/main").encode()]):
                draft_pr.remote_guard(plan)
        with patch.object(draft_pr, "git", return_value=b"https://github.com/elsewhere/openapi-directory.git"), self.assertRaisesRegex(ValueError, "restricted"):
            draft_pr.remote_guard(plan)
        with patch.object(draft_pr, "git", side_effect=[b"https://github.com/ontola/openapi-directory.git"] * 2 + [b"0000000000000000000000000000000000000000\trefs/heads/main"]), self.assertRaisesRegex(ValueError, "main advanced"):
            draft_pr.remote_guard(plan)

    def test_secondary_fetch_or_push_urls_are_never_used_for_publication(self):
        plan = self.plan()
        one = b"https://github.com/ontola/openapi-directory.git"
        two = one + b"\nhttps://github.com/elsewhere/repo.git\n"
        for responses in ([two], [one, two]):
            with self.subTest(responses=responses), patch.object(draft_pr, "git", side_effect=responses), self.assertRaisesRegex(ValueError, "unambiguous"):
                draft_pr.remote_guard(plan)

    def test_real_atomic_branch_creation_verified_draft_and_unchanged_checkout(self):
        self.remote()
        plan = self.plan()
        before = (self.git("rev-parse", "HEAD"), self.git("status", "--porcelain"))
        with patch.object(draft_pr, "remote_guard"), patch.object(draft_pr, "gh_json", side_effect=self.fake_github(plan)) as gh:
            result = draft_pr.publish(plan, self.cache)
        self.assertEqual(result["status"], "draft_created")
        self.assertEqual(result["url"], "https://github.com/ontola/openapi-directory/pull/42")
        self.assertEqual(sum(call.args[1:2] == ("POST",) for call in gh.call_args_list), 1)
        self.assertEqual(before, (self.git("rev-parse", "HEAD"), self.git("status", "--porcelain")))
        self.assertEqual(self.git("ls-remote", "origin", "refs/heads/" + plan["branch"]).split()[0], result["head"])
        # A second attempt observes the existing branch and cannot overwrite it.
        with patch.object(draft_pr, "remote_guard"), patch.object(draft_pr, "existing_pr", return_value=[]), patch.object(draft_pr, "commit_plan") as commit:
            self.assertEqual(draft_pr.publish(plan, self.cache)["status"], "existing_branch")
        commit.assert_not_called()

    def test_unknown_post_outcome_and_rejected_push_guard_against_retry(self):
        for failure_stage in ("push", "create_pull_request"):
            with self.subTest(stage=failure_stage):
                plan = self.plan()
                blocked = self.cache / "publication/example/blocked.json"
                blocked.unlink(missing_ok=True)
                original_git = draft_pr.git
                def run(*args, **kwargs):
                    if args[0] == "ls-remote":
                        return b""
                    if args[0] == "push":
                        if failure_stage == "push":
                            raise subprocess.CalledProcessError(1, ["git", "push"], stderr=b"vendor example secret")
                        return b""
                    return original_git(*args, **kwargs)
                with patch.object(draft_pr, "remote_guard"), patch.object(draft_pr, "existing_pr", return_value=[]), patch.object(draft_pr, "git", side_effect=run), patch.object(draft_pr, "gh_json", side_effect=TimeoutError("unknown outcome")):
                    with self.assertRaises(draft_pr.PublicationFailure):
                        draft_pr.publish(plan, self.cache)
                receipt = json.loads(blocked.read_text())
                self.assertEqual(receipt["stage"], failure_stage)
                self.assertNotIn("vendor example", blocked.read_text())
                with patch.object(draft_pr, "remote_guard") as remote, self.assertRaisesRegex(ValueError, "previous publication failed"):
                    draft_pr.publish(plan, self.cache)
                remote.assert_not_called()

    def test_concurrent_remote_branch_creation_is_never_overwritten(self):
        self.remote()
        plan = self.plan()
        original_git = draft_pr.git
        def run(*args, **kwargs):
            if args[0] == "push":
                self.git("push", "origin", self.base + ":refs/heads/" + plan["branch"])
            return original_git(*args, **kwargs)
        with patch.object(draft_pr, "remote_guard"), patch.object(draft_pr, "existing_pr", return_value=[]), patch.object(draft_pr, "git", side_effect=run), patch.object(draft_pr, "gh_json") as gh:
            with self.assertRaises(draft_pr.PublicationFailure):
                draft_pr.publish(plan, self.cache)
        gh.assert_not_called()
        self.assertEqual(self.git("ls-remote", "origin", "refs/heads/" + plan["branch"]).split()[0], self.base)

    def test_wrong_created_head_records_url_without_claiming_verified_success(self):
        self.remote()
        plan = self.plan()
        output = io.StringIO()
        with patch.object(draft_pr, "remote_guard"), patch.object(draft_pr, "gh_json", side_effect=self.fake_github(plan, bad_head=True)), contextlib.redirect_stdout(output):
            self.assertEqual(draft_pr.main(["--source", "example", "--base", self.base, "--cache", str(self.cache), "--publish"]), 1)
        result = json.loads(output.getvalue())
        self.assertEqual(result["stage"], "verify_pull_request")
        self.assertEqual(result["created_url"], "https://github.com/ontola/openapi-directory/pull/42")
        self.assertTrue((self.cache / "publication/example/blocked.json").exists())

    def test_post_push_base_change_prevents_pr_creation(self):
        self.remote()
        plan = self.plan()
        with patch.object(draft_pr, "remote_guard", side_effect=[None, None, ValueError("main advanced")]), patch.object(draft_pr, "existing_pr", return_value=[]), patch.object(draft_pr, "gh_json") as gh:
            with self.assertRaises(draft_pr.PublicationFailure):
                draft_pr.publish(plan, self.cache)
        gh.assert_not_called()
        self.assertEqual(json.loads((self.cache / "publication/example/blocked.json").read_text())["stage"], "post_push_base_check")

    def test_retained_lock_prevents_concurrent_or_interrupted_publication(self):
        plan = self.plan()
        directory = self.cache / "publication/example"
        directory.mkdir(parents=True)
        (directory / "publishing.lock").write_text("prior attempt")
        with patch.object(draft_pr, "remote_guard") as remote, self.assertRaisesRegex(ValueError, "running or interrupted"):
            draft_pr.publish(plan, self.cache)
        remote.assert_not_called()

    def test_invalid_source_ids_groups_targets_and_cross_provider_groups_stop_fetch(self):
        original = {"schema_version": 1, "sources": copy.deepcopy(self.sources)}
        cases = []
        for key, value in (("id", "../escape"), ("publication_group", "../escape"),
                           ("target", "APIs/example.com/../other.com/openapi.yaml"),
                           ("target", "APIs//example.com/1.0/openapi.yaml")):
            manifest = copy.deepcopy(original)
            manifest["sources"][0][key] = value
            cases.append(manifest)
        manifest = copy.deepcopy(original)
        manifest["sources"][0]["publication_group"] = "group"
        manifest["sources"].append({**manifest["sources"][0], "id": "other", "provider": "other.com"})
        cases.append(manifest)
        for index, manifest in enumerate(cases):
            with self.subTest(case=index), self.assertRaises(ValueError):
                draft_pr.select_sources(manifest, manifest["sources"][0]["id"])

    def test_created_pr_identity_draft_base_and_complete_files_must_match(self):
        self.remote()
        plan = self.plan()
        commit = draft_pr.commit_plan(plan)
        self.git("push", "origin", commit + ":refs/heads/" + plan["branch"])
        original = self.fake_github(plan)("pulls", "POST", {"draft": True, "base": "main", "head": plan["branch"]})
        changes = []
        for field, value in (("draft", False), ("state", "closed"), ("html_url", "https://example.com/pr")):
            changed = copy.deepcopy(original)
            changed[field] = value
            changes.append(changed)
        for side, key, value in (("base", "ref", "other"), ("head", "ref", "other"),
                                 ("base", "repo", {"full_name": "elsewhere/repo"}),
                                 ("head", "repo", {"full_name": "elsewhere/repo"})):
            changed = copy.deepcopy(original)
            changed[side][key] = value
            changes.append(changed)
        for index, pr in enumerate(changes):
            with self.subTest(change=index), self.assertRaisesRegex(ValueError, "identity/state"):
                draft_pr.verify_created_pr(pr, plan, commit)
        with patch.object(draft_pr, "pages", return_value=[{"filename": "unexpected/file"}]), self.assertRaisesRegex(ValueError, "file list"):
            draft_pr.verify_created_pr(original, plan, commit)

    def test_offline_ci_validates_real_sparse_commit_without_vendor_network(self):
        plan = self.plan()
        commit = draft_pr.commit_plan(plan)
        self.git("sparse-checkout", "init", "--cone")
        self.git("sparse-checkout", "set", "maintenance")
        self.fetch_mock.reset_mock()
        with patch.object(draft_pr, "gh_json") as gh:
            result = draft_pr.validate_commit(self.base, commit, plan["branch"])
        self.assertEqual(result["status"], "draft_commit_validated")
        self.assertEqual(result["files"], sorted(plan["files"]))
        self.fetch_mock.assert_not_called()
        gh.assert_not_called()

    def modified_commit(self, head, path, content, mode="100644"):
        # A second private index creates an intentionally incorrect single-parent
        # candidate to exercise CI independently of the production builder.
        import os
        with tempfile.TemporaryDirectory() as directory:
            env = {**os.environ, "GIT_INDEX_FILE": str(Path(directory) / "index")}
            draft_pr.git("read-tree", head, env=env)
            blob = draft_pr.git("hash-object", "-w", "--stdin", data=content.encode()).decode().strip()
            draft_pr.git("update-index", "--add", "--cacheinfo", mode + "," + blob + "," + path, env=env)
            tree = draft_pr.git("write-tree", env=env).decode().strip()
            return draft_pr.git("commit-tree", tree, "-p", self.base, data=b"altered candidate\n").decode().strip()

    def test_offline_ci_rejects_unrelated_tree_config_and_native_defects(self):
        plan = self.plan()
        original = draft_pr.commit_plan(plan)
        path = plan["sources"][0]["destination"]
        invalid = copy.deepcopy(self.new)
        invalid["components"]["schemas"]["Choice"]["oneOf"] = []
        manifest = json.loads(plan["files"][draft_pr.MANIFEST])
        manifest["sources"][0]["url"] = "https://elsewhere.example/spec"
        cases = [("README.md", "unrelated change", "100644"),
                 (path, json.dumps(invalid), "100644"),
                 (draft_pr.MANIFEST, json.dumps(manifest), "100644"),
                 (path, plan["files"][path], "120000")]
        for path, content, mode in cases:
            head = self.modified_commit(original, path, content, mode)
            with self.subTest(path=path, mode=mode), self.assertRaises(ValueError):
                draft_pr.validate_commit(self.base, head, plan["branch"])

    def test_offline_ci_requires_exact_base_and_configured_group(self):
        plan = self.plan()
        commit = draft_pr.commit_plan(plan)
        with self.assertRaisesRegex(ValueError, "configured publication group"):
            draft_pr.validate_commit(self.base, commit, "codex/official-update-unregistered")
        self.put("notes.txt", "main advanced\n")
        advanced = self.commit()
        with self.assertRaisesRegex(ValueError, "comparison base/head changed"):
            draft_pr.validate_commit(advanced, commit, plan["branch"])

    # --- Generations after verified merged generated branches (design #238) ---

    def merged_generation(self, message=None, squash=False, open_pr=False, unmerged=False, move_tip=False):
        """Create generation 1 on the remote and (optionally) merge it into main."""
        self.remote()
        first = self.plan()
        commit = draft_pr.commit_plan(first)
        if message is not None:
            tree = self.git("rev-parse", commit + "^{tree}")
            commit = self.git("commit-tree", tree, "-p", self.base, "-m", message)
        self.git("push", "origin", commit + ":refs/heads/" + first["branch"])
        tip = commit
        if move_tip:
            tip = self.git("commit-tree", self.git("rev-parse", commit + "^{tree}"), "-p", commit, "-m", "later")
            self.git("push", "-f", "origin", tip + ":refs/heads/" + first["branch"])
        if squash:
            merged = self.git("commit-tree", self.git("rev-parse", commit + "^{tree}"), "-p", self.base, "-m", "squash")
        elif open_pr or unmerged:
            merged = self.base
        else:
            merged = self.git("commit-tree", self.git("rev-parse", commit + "^{tree}"), "-p", self.base, "-p", commit, "-m", "merge")
        self.git("push", "-f", "origin", merged + ":refs/heads/main")
        self.git("reset", "-q", "--hard", merged)
        self.base = merged
        pr = {"number": 7, "html_url": "https://github.com/ontola/openapi-directory/pull/7",
              "state": "open" if open_pr else "closed",
              "merged_at": None if (open_pr or unmerged) else "2026-10-08T12:00:00Z",
              "merge_commit_sha": merged,
              "head": {"ref": first["branch"], "sha": commit, "repo": {"full_name": draft_pr.REPOSITORY}}}
        return first, commit, pr

    def github_with(self, pr, created=None):
        def respond(endpoint, method="GET", payload=None):
            if "pulls?state=all&head=" in endpoint:
                return [pr] if "page=1" in endpoint else []
            if created is not None:
                return created(endpoint, method, payload)
            return []
        return respond

    def test_generated_branch_names_parse_strictly(self):
        self.assertEqual(draft_pr.branch_name("github-public-rest"), "codex/official-update-github-public-rest")
        self.assertEqual(draft_pr.branch_name("hcp-hvn", 2), "codex/official-update-hcp-hvn--g2")
        self.assertEqual(draft_pr.branch_group("codex/official-update-hcp-hvn"), ("hcp-hvn", 1))
        self.assertEqual(draft_pr.branch_group("codex/official-update-hcp-hvn--g12"), ("hcp-hvn", 12))
        for bad in ("codex/official-update-hcp-hvn--g02", "codex/official-update-hcp-hvn--g1",
                    "codex/official-update-hcp-hvn--g", "codex/official-update-x--g2--g3",
                    "claude/official-update-hcp-hvn", None):
            self.assertEqual(draft_pr.branch_group(bad), (None, None), bad)
        with self.assertRaises(ValueError):
            draft_pr.branch_name("x", 0)

    def test_reserved_generation_suffix_in_source_ids_is_rejected(self):
        manifest = {"schema_version": 1, "sources": [dict(self.sources[0], id="example--g2")]}
        with self.assertRaisesRegex(ValueError, "Unsafe source ID"):
            draft_pr.select_sources(manifest, "example--g2")
        manifest = {"schema_version": 1, "sources": [dict(self.sources[0], publication_group="example--g3")]}
        with self.assertRaisesRegex(ValueError, "Unsafe publication group"):
            draft_pr.select_sources(manifest, "example")

    def test_verified_merged_generation_allows_g2_with_observation_and_real_push(self):
        first, commit, pr = self.merged_generation()
        self.specs["example"] = copy.deepcopy(self.new)
        self.specs["example"]["paths"]["/items/{id}"]["get"]["responses"]["200"]["description"] = "Newer response"
        plan = self.plan()
        with patch.object(draft_pr, "gh_json", side_effect=self.github_with(pr)):
            chosen = draft_pr.next_generation(plan, self.cache)
        self.assertEqual(chosen["branch"], "codex/official-update-example--g2")
        self.assertEqual(chosen["seal"], draft_pr.seal(chosen))
        draft_pr.verify_plan(chosen)
        observation = json.loads((self.cache / "publication/example/retired/g1.json").read_text())
        self.assertTrue(observation["not_a_creation_receipt"])
        self.assertEqual((observation["tip"], observation["number"]), (commit, 7))
        new_pr = {}
        def created(endpoint, method, payload):
            if method == "POST" or endpoint.endswith("/pulls/42"):
                head = self.git("ls-remote", "origin", "refs/heads/" + chosen["branch"]).split()[0]
                return {"number": 42, "html_url": "https://github.com/ontola/openapi-directory/pull/42",
                        "draft": True, "state": "open",
                        "head": {"ref": chosen["branch"], "sha": head, "repo": {"full_name": draft_pr.REPOSITORY}},
                        "base": {"ref": "main", "sha": self.base, "repo": {"full_name": draft_pr.REPOSITORY}}}
            if "/pulls/42/files" in endpoint:
                return [{"filename": path} for path in chosen["files"]]
            return []
        with patch.object(draft_pr, "remote_guard"), patch.object(draft_pr, "gh_json", side_effect=self.github_with(pr, created)):
            result = draft_pr.publish(chosen, self.cache)
        self.assertEqual(result["status"], "draft_created")
        # Generation 1 is untouched; generation 2 is a new single-parent commit on main.
        self.assertEqual(self.git("ls-remote", "origin", "refs/heads/" + first["branch"]).split()[0], commit)
        self.assertEqual(self.git("rev-list", "--parents", "-n", "1", result["head"]).split()[1:], [self.base])
        validated = draft_pr.validate_commit(self.base, result["head"], chosen["branch"])
        self.assertEqual(validated["status"], "draft_commit_validated")

    def test_unverified_generations_hold_without_new_branch(self):
        cases = {"open": dict(open_pr=True), "closed_unmerged": dict(unmerged=True),
                 "squash": dict(squash=True), "moved_tip": dict(move_tip=True),
                 "foreign_message": dict(message="Hand-written change")}
        for name, options in cases.items():
            with self.subTest(case=name):
                self.setUp_again()
                first, commit, pr = self.merged_generation(**options)
                if name == "moved_tip":
                    pr["head"]["sha"] = commit
                self.specs["example"] = copy.deepcopy(self.new)
                self.specs["example"]["info"]["description"] = "Changed again"
                plan = self.plan()
                with patch.object(draft_pr, "gh_json", side_effect=self.github_with(pr)):
                    chosen = draft_pr.next_generation(plan, self.cache)
                self.assertEqual(chosen["branch"], first["branch"])
                self.assertFalse((self.cache / "publication/example/retired").exists())
                with patch.object(draft_pr, "remote_guard"), patch.object(draft_pr, "existing_pr", return_value=[]), \
                        patch.object(draft_pr, "gh_json", side_effect=self.github_with(pr)), \
                        patch.object(draft_pr, "commit_plan") as build:
                    self.assertEqual(draft_pr.publish(chosen, self.cache)["status"], "existing_branch")
                build.assert_not_called()

    def test_g2_plan_is_reverified_under_lock_and_held_if_generation_changed(self):
        first, commit, pr = self.merged_generation()
        self.specs["example"] = copy.deepcopy(self.new)
        self.specs["example"]["info"]["description"] = "Changed again"
        plan = self.plan()
        with patch.object(draft_pr, "gh_json", side_effect=self.github_with(pr)):
            chosen = draft_pr.next_generation(plan, self.cache)
        reopened = dict(pr, state="open", merged_at=None)
        with patch.object(draft_pr, "remote_guard"), patch.object(draft_pr, "existing_pr", return_value=[]), \
                patch.object(draft_pr, "gh_json", side_effect=self.github_with(reopened)), \
                patch.object(draft_pr, "commit_plan") as build:
            self.assertEqual(draft_pr.publish(chosen, self.cache)["status"], "existing_branch")
        build.assert_not_called()

    def test_offline_ci_accepts_only_valid_generations_of_configured_groups(self):
        plan = self.plan()
        commit = draft_pr.commit_plan(plan)
        self.assertEqual(draft_pr.validate_commit(self.base, commit, plan["branch"] + "--g2")["status"],
                         "draft_commit_validated")
        for bad in ("--g02", "--g1", "--g"):
            with self.subTest(suffix=bad), self.assertRaisesRegex(ValueError, "configured publication group"):
                draft_pr.validate_commit(self.base, commit, plan["branch"] + bad)
        with self.assertRaisesRegex(ValueError, "configured publication group"):
            draft_pr.validate_commit(self.base, commit, "codex/official-update-unregistered--g2")

    def setUp_again(self):
        self.doCleanups()
        self.setUp()


if __name__ == "__main__":
    unittest.main()
