import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import update


def document(version="1.0"):
    return {"openapi": "3.1.0", "info": {"title": "Test API", "version": version},
            "paths": {"/items/{id}": {"parameters": [{"$ref": "#/components/parameters/Id"}],
                                      "get": {"responses": {"200": {"description": "OK"}}}}},
            "components": {"parameters": {"Id": {"name": "id", "in": "path", "required": True,
                                                    "schema": {"type": "string"}}},
                           "schemas": {"Choice": {"oneOf": [{"type": "string"}, {"type": "null"}]}}}}


class UpdaterTests(unittest.TestCase):
    def test_fixed_version_schema_and_security_changes_are_detected(self):
        old = document()
        new = copy.deepcopy(old)
        new["components"]["parameters"]["Id"]["schema"]["minLength"] = 2
        self.assertEqual(update.compare(old, new)["status"], "changed")
        new = copy.deepcopy(old)
        new["security"] = []
        self.assertEqual(update.compare(old, new)["status"], "changed")

    def test_key_order_is_not_a_change(self):
        old = document()
        new = dict(reversed(list(old.items())))
        self.assertEqual(update.compare(old, new)["status"], "matches_source")

    def test_curation_survives_without_perpetual_drift(self):
        old = document()
        old["info"].update({key: "curated" for key in update.CURATION})
        old["info"]["contact"] = {"x-twitter": "test"}
        old["info"]["x-conversion"] = ["Previous snapshot"]
        old["externalDocs"] = {"url": "https://example.com"}
        old["tags"] = [{"name": "curated"}, {"name": "vendor", "description": "curated description"}]
        new = document()
        new["tags"] = [{"name": "vendor"}, {"name": "new"}]
        result = update.preserve_curation(old, new)
        for key in update.CURATION:
            self.assertEqual(result["info"][key], old["info"][key])
        self.assertEqual(result["info"]["contact"]["x-twitter"], "test")
        self.assertEqual(result["externalDocs"], old["externalDocs"])
        self.assertEqual(len(result["tags"]), 3)
        self.assertEqual(update.compare(result, new)["status"], "matches_source")
        new["tags"][0]["description"] = "Changed by vendor"
        self.assertEqual(update.compare(result, new)["status"], "changed")

    def test_new_version_directory_and_unsafe_versions(self):
        source = {"target": "APIs/example.com/service/1.0/openapi.yaml",
                  "provider": "example.com", "version_policy": "vendor"}
        self.assertEqual(str(update.destination(source, document("2.0"))),
                         "APIs/example.com/service/2.0/openapi.yaml")
        for version in ("", "..", "../escape", "2026/10"):
            with self.assertRaises(ValueError):
                update.destination(source, document(version))

    def test_array_pointer_escaped_tokens_and_referenced_parameters(self):
        spec = document()
        self.assertEqual(update.pointer(spec, "#/components/schemas/Choice/oneOf/1"), {"type": "null"})
        self.assertEqual(update.pointer({"a/b": {"~": ["yes"]}}, "#/a~1b/~0/0"), "yes")
        with self.assertRaises(ValueError):
            update.pointer(spec, "#/components/schemas/Choice/oneOf/-1")
        self.assertEqual(update.validate_document(spec), [])
        spec["components"]["parameters"]["Id"]["name"] = "wrong"
        self.assertTrue(any("mismatched" in e for e in update.validate_document(spec)))

    def test_missing_responses_and_broken_references_fail(self):
        spec = document()
        spec["paths"]["/items/{id}"]["get"]["responses"] = {}
        self.assertTrue(update.validate_document(spec))
        spec = document()
        del spec["components"]["parameters"]["Id"]
        self.assertTrue(update.validate_document(spec))

    def test_external_schema_refs_block_but_snippets_and_example_data_do_not(self):
        spec = document()
        spec["x-fern-examples"] = [{"code": {"$ref": "snippet.ts"}}]
        spec["components"]["schemas"]["Choice"]["example"] = {"$ref": "literal payload"}
        self.assertEqual(update.validate_document(spec), [])
        spec["components"]["schemas"]["x-real-schema"] = {"$ref": "common.yaml#/Thing"}
        self.assertTrue(any("bundling" in e for e in update.validate_document(spec)))

    def test_timestamp_versions_remain_strings_and_html_is_rejected(self):
        raw = b'openapi: 3.1.0\ninfo:\n  title: Test\n  version: 2026-10-02\npaths: {}\n'
        self.assertEqual(update.parse(raw)["info"]["version"], "2026-10-02")
        with self.assertRaises(ValueError):
            update.parse(b"<html>Not Found</html>")

    def test_json_and_yaml_preserve_boolean_like_property_names(self):
        spec = document()
        spec["components"]["schemas"]["Workflow"] = {"type": "object", "properties": {
            "on": {"type": "string"}, "off": {"type": "string"}, "yes": {"type": "string"}}}
        for raw in (json.dumps(spec).encode(),
                    b'openapi: 3.1.0\ninfo: {title: Test, version: "1"}\npaths: {}\n'
                    b'components:\n  schemas:\n    Workflow:\n      properties:\n'
                    b'        on: {type: string}\n        off: {type: string}\n        yes: {type: string}\n'):
            parsed = update.parse(raw)
            self.assertEqual(set(parsed["components"]["schemas"]["Workflow"]["properties"]), {"on", "off", "yes"})
            update.canonical(parsed)

    def test_import_records_provenance_without_mutating_source(self):
        new = document()
        before = copy.deepcopy(new)
        metadata = {"url": "https://vendor.example/openapi.json", "revision": "abc",
                    "sha256": "def", "fetched_at": "today"}
        source = {"target": "APIs/example.com/1.0/openapi.yaml"}
        result = update.import_document(source, new, metadata, None)
        self.assertEqual(new, before)
        self.assertIn("abc", result["info"]["x-conversion"][0])
        self.assertEqual(result["info"]["x-origin"][0]["version"], "3.1")
        with self.assertRaises(ValueError):
            update.import_document({**source, "import_blocker": "Not bundled"}, new, metadata, None)

    def test_failed_fetch_does_not_advance_success_and_subset_report_keeps_other_apis(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.json"
            report.write_text(json.dumps({"sources": [
                {"id": "one", "last_successful_fetch": "yesterday", "last_successful_validation": "yesterday"},
                {"id": "two", "status": "matches_source"}]}))
            results = [{"id": "one", "status": "failed", "checked_at": "today"}]
            with patch.object(update, "git", return_value=b"commit\n"):
                update.write_report(report, results, "origin/main")
            rows = {row["id"]: row for row in json.loads(report.read_text())["sources"]}
            self.assertEqual(rows["one"]["last_successful_fetch"], "yesterday")
            self.assertEqual(rows["one"]["last_successful_validation"], "yesterday")
            self.assertIn("two", rows)
            with patch.object(update, "fetch", side_effect=OSError("Network unavailable")):
                result = update.audit({"id": "one", "target": "APIs/example.com/1.0/openapi.yaml"},
                                      "origin/main", Path(directory))
            self.assertEqual(result["status"], "failed")
            self.assertNotIn("last_successful_fetch", result)

    def test_changed_referenced_content_is_detected_after_bundling(self):
        # Bundlers supply resolved documents to the same comparison function.
        old = document()
        new = document()
        new["components"]["schemas"]["Choice"]["oneOf"].append({"type": "integer"})
        self.assertEqual(update.compare(old, new)["status"], "changed")

    def test_existing_destination_is_preferred_after_version_bump(self):
        source = {"id": "test", "target": "APIs/example.com/1.0/openapi.yaml",
                  "provider": "example.com", "version_policy": "vendor"}
        raw = json.dumps(document("2.0")).encode()
        metadata = {"sha256": update.sha256(raw), "fetched_at": "today"}
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(update, "fetch", return_value=(raw, metadata)), \
                 patch.object(update, "stored", return_value=document("2.0")) as stored:
                result = update.audit(source, "origin/main", Path(directory))
            self.assertEqual(result["status"], "matches_source")
            stored.assert_called_once_with("APIs/example.com/2.0/openapi.yaml", "origin/main")


if __name__ == "__main__":
    unittest.main()
