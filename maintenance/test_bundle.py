import copy
import io
import json
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import bundle
import update
from test_update import document


def archive_files(files, extra=None):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as tar:
        for path, raw in files.items():
            member = tarfile.TarInfo("vendor-revision/" + path)
            member.size = len(raw)
            tar.addfile(member, io.BytesIO(raw))
        if extra:
            tar.addfile(extra)
    return output.getvalue()


class BundleTests(unittest.TestCase):
    def test_pinned_real_bundle_detects_reference_changes_and_handles_cycles_and_array_pointers(self):
        spec = document()
        spec["components"]["schemas"]["Item"] = {"$ref": "common.yaml#/Node"}
        spec["paths"]["/items/{id}"]["get"]["responses"]["200"]["content"] = {
            "application/json": {"schema": {"$ref": "#/components/schemas/Item"}}}
        raw = json.dumps(spec).encode()
        common = {"Node": {"type": "object", "properties": {
            "next": {"$ref": "#/Node"}, "label": {"$ref": "#/Choices/oneOf/1"}}},
                  "Choices": {"oneOf": [{"type": "integer"}, {"type": "string", "minLength": 2}]}}
        source = {"id": "test", "github": {"repository": "vendor/api", "path": "spec/openapi.yaml"},
                  "bundling": {"tool": "redocly", "version": bundle.TOOL_VERSION, "root": "spec"}}
        results = []
        with tempfile.TemporaryDirectory() as directory:
            for minimum in (2, 7):
                common["Choices"]["oneOf"][1]["minLength"] = minimum
                archive = archive_files({"spec/openapi.yaml": raw,
                                         "spec/common.yaml": json.dumps(common).encode()})
                request = Mock(return_value=(archive, {}))
                metadata = {"revision": "a" * 40, "sha256": update.sha256(raw)}
                bundled, step = bundle.prepare(source, raw, metadata, Path(directory), request, update.Loader)
                request.assert_called_once_with("https://codeload.github.com/vendor/api/tar.gz/" + "a" * 40)
                parsed = update.parse(bundled)
                self.assertEqual(update.validate_document(parsed), [])
                self.assertTrue(all(r.startswith("#") for r in update.reference_objects(parsed)))
                self.assertEqual(len(metadata["bundling"]["files"]), 2)
                self.assertIn(metadata["snapshot_sha256"], step)
                self.assertEqual(metadata["bundling"]["warnings"], 0)
                results.append((parsed, copy.deepcopy(metadata)))
            self.assertNotEqual(results[0][1]["snapshot_sha256"], results[1][1]["snapshot_sha256"])
            self.assertEqual(results[0][1]["sha256"], results[1][1]["sha256"])
            comparison = update.compare(results[0][0], results[1][0])
            self.assertEqual(comparison["status"], "changed")
            self.assertEqual(comparison["added_paths"], [])
            self.assertEqual(comparison["removed_paths"], [])

    def test_reference_preflight_rejects_missing_remote_absolute_and_escaping_files(self):
        for ref in ("missing.yaml#/Thing", "https://vendor.example/schema.json", "/tmp/schema.yaml",
                    "../../escape.yaml", "%2Ftmp/schema.yaml", "common.yaml?version=latest"):
            files = {"spec/openapi.yaml": json.dumps({"$ref": ref}).encode()}
            with self.subTest(ref=ref), self.assertRaises(ValueError):
                bundle.reference_graph(files, "spec/openapi.yaml", update.Loader)

    def test_archive_preflight_rejects_links_traversal_and_duplicate_members(self):
        for name, kind in (("vendor-revision/spec/link.yaml", tarfile.SYMTYPE),
                           ("../spec/escape.yaml", tarfile.REGTYPE),
                           ("/absolute.yaml", tarfile.REGTYPE),
                           ("vendor-revision/spec/openapi.yaml", tarfile.REGTYPE)):
            extra = tarfile.TarInfo(name)
            extra.type = kind
            extra.linkname = "/tmp/escape"
            archive = archive_files({"spec/openapi.yaml": b"{}"}, extra)
            with self.subTest(name=name), self.assertRaises(ValueError):
                bundle.snapshot_files(archive, "spec")

    def test_source_archive_mismatch_fails_before_running_bundler(self):
        source = {"id": "test", "github": {"repository": "vendor/api", "path": "spec/openapi.yaml"},
                  "bundling": {"tool": "redocly", "version": bundle.TOOL_VERSION, "root": "spec"}}
        with tempfile.TemporaryDirectory() as directory:
            request = Mock(return_value=(archive_files({"spec/openapi.yaml": b"wrong"}), {}))
            with self.assertRaisesRegex(ValueError, "independently fetched"):
                bundle.prepare(source, b"expected", {"revision": "a" * 40}, Path(directory), request, update.Loader)


if __name__ == "__main__":
    unittest.main()
