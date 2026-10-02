import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import update
from test_update import document


class SampleTests(unittest.TestCase):
    def setUp(self):
        self.source = {"id": "samples", "target": "APIs/example.com/1.0/openapi.yaml",
                       "provider": "example.com", "version_policy": "vendor",
                       "github": {"repository": "vendor/docs", "path": "api/openapi.yaml"},
                       "code_samples": {"kind": "fern", "root": "api/snippets", "extensions": [".ts"]}}
        self.spec = document()
        self.sample = {"sdk": "typescript", "code": {"$ref": "./snippets/example.ts"}}
        self.spec["paths"]["/items/{id}"]["get"]["x-fern-examples"] = [
            {"code-samples": [copy.deepcopy(self.sample), copy.deepcopy(self.sample)]}]
        self.raw = json.dumps(self.spec).encode()
        self.metadata = {"revision": "a" * 40, "sha256": update.sha256(self.raw),
                         "url": "https://vendor.example/openapi.yaml", "fetched_at": "today"}

    def prepare(self, cache, content):
        metadata = copy.deepcopy(self.metadata)
        with patch.object(update, "request", return_value=(content, {"url": "https://vendor.example/example.ts"})) as request:
            spec, steps = update.prepare_document(self.source, self.raw, metadata, cache)
        return spec, metadata, steps, request

    def test_pinned_text_snapshot_and_snippet_only_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            code = b'// Example\r\nconsole.log("caf\xc3\xa9");\n'
            old, metadata, steps, request = self.prepare(cache, code)
            request.assert_called_once_with("https://raw.githubusercontent.com/vendor/docs/" + "a" * 40
                                            + "/api/snippets/example.ts")
            samples = old["paths"]["/items/{id}"]["get"]["x-fern-examples"][0]["code-samples"]
            self.assertEqual([s["code"] for s in samples], [code.decode(), code.decode()])
            root = cache / "samples" / metadata["snapshot_sha256"]
            self.assertEqual((root / "repository/api/snippets/example.ts").read_bytes(), code)
            self.assertEqual((root / "repository/api/openapi.yaml").read_bytes(), self.raw)
            hashes = json.loads((root / "source-files.json").read_text())
            self.assertEqual(hashes["api/snippets/example.ts"], update.sha256(code))
            self.assertEqual(metadata["code_samples"]["references"], 2)
            self.assertIn("without executing", steps[0])
            self.assertEqual(update.parse(self.raw), self.spec)
            self.assertEqual(update.validate_document(old), [])
            new, new_metadata, _, _ = self.prepare(cache, b'console.log("changed");\n')
            self.assertNotEqual(metadata["snapshot_sha256"], new_metadata["snapshot_sha256"])
            self.assertEqual(update.compare(old, new)["status"], "changed")
            same, _, _, _ = self.prepare(cache, code)
            self.assertEqual(update.compare(old, same)["status"], "matches_source")
            metadata["transformations"] = steps
            result = update.import_document(self.source, old, metadata, None)
            self.assertIn(metadata["snapshot_sha256"], result["info"]["x-conversion"][1])

    def test_scope_does_not_interpret_schema_or_literal_payload_references(self):
        self.spec["components"]["schemas"]["Choice"]["example"] = {"$ref": "literal.ts"}
        self.spec["x-other-extension"] = {"$ref": "unrelated.ts"}
        self.raw = json.dumps(self.spec).encode()
        with tempfile.TemporaryDirectory() as directory:
            spec, _, _, request = self.prepare(Path(directory), b'// sample')
        self.assertEqual(spec["components"], self.spec["components"])
        self.assertEqual(spec["x-other-extension"], self.spec["x-other-extension"])
        self.assertEqual(request.call_count, 1)

    def test_real_fetch_helper_contract(self):
        # Exercise request(), not a mock of its return shape: the importer must
        # consume its (bytes, metadata) pair for supporting artifacts too.
        from unittest.mock import MagicMock
        response = MagicMock()
        response.url = "https://raw.githubusercontent.com/vendor/docs/" + "a" * 40 + "/api/snippets/example.ts"
        response.headers = {"ETag": "test-etag"}
        response.read.return_value = b'// actual helper contract\n'
        response.__enter__.return_value = response
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(update.urllib.request, "urlopen", return_value=response):
            metadata = copy.deepcopy(self.metadata)
            spec, _ = update.prepare_document(self.source, self.raw, metadata, Path(directory))
        self.assertEqual(metadata["code_samples"]["files"]["api/snippets/example.ts"]["etag"], "test-etag")
        self.assertEqual(spec["paths"]["/items/{id}"]["get"]["x-fern-examples"][0]["code-samples"][0]["code"],
                         '// actual helper contract\n')

    def test_unsafe_or_changed_artifacts_block_before_fetching(self):
        for ref in ("https://other.example/a.ts", "//other/a.ts", "./snippets/a.ts?x=1",
                    "./snippets/a.ts#fragment", "../escape.ts", "/api/snippets/a.ts",
                    "./snippets/a.json", "./snippets/%2e%2e/a.ts", "./snippets/../../../a.ts"):
            spec = copy.deepcopy(self.spec)
            spec["paths"]["/items/{id}"]["get"]["x-fern-examples"][0]["code-samples"][0]["code"]["$ref"] = ref
            with tempfile.TemporaryDirectory() as directory, patch.object(update, "request") as request:
                with self.assertRaises(ValueError):
                    update.prepare_document(self.source, json.dumps(spec).encode(), self.metadata, Path(directory))
                request.assert_not_called()

    def test_missing_or_invalid_utf8_artifact_is_a_failed_audit_with_raw_source_retained(self):
        for error in (OSError("Missing snippet"), UnicodeDecodeError("utf8", b'\xff', 0, 1, "invalid")):
            with tempfile.TemporaryDirectory() as directory, \
                 patch.object(update, "fetch", return_value=(self.raw, copy.deepcopy(self.metadata))), \
                 patch.object(update, "request", side_effect=error):
                result = update.audit(self.source, "origin/main", Path(directory))
                self.assertEqual(result["status"], "failed")
                self.assertEqual(result["last_successful_fetch"], "today")
                self.assertNotIn("last_successful_comparison", result)
                self.assertEqual((Path(directory) / "samples" / self.metadata["sha256"] / "source").read_bytes(), self.raw)

    def test_yaml_scientific_bounds_are_numbers_and_quoted_values_remain_strings(self):
        raw = b'''openapi: 3.1.0
info: {title: Scientific bounds, version: '1.0'}
paths: {}
components:
  schemas:
    Rate: {type: number, minimum: 1e-08, maximum: 1e+09, default: 1E2}
    Literal: {type: string, default: '1e-08'}
'''
        parsed = update.parse(raw)
        self.assertEqual(parsed["components"]["schemas"]["Rate"]["minimum"], 1e-8)
        self.assertEqual(parsed["components"]["schemas"]["Rate"]["maximum"], 1e9)
        self.assertEqual(parsed["components"]["schemas"]["Rate"]["default"], 100)
        self.assertEqual(parsed["components"]["schemas"]["Literal"]["default"], "1e-08")
        self.assertEqual(update.validate_document(parsed), [])
        self.assertEqual(update.compare(parsed, update.parse(json.dumps(parsed).encode()))["status"], "matches_source")
