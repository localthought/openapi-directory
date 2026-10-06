import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import embedded
import update


SOURCE = {"id": "embedded", "target": "APIs/example.com/1.0/openapi.yaml", "url": "https://vendor.example/reference",
          "embedded_document": {"format": "next-data-json-string", "pointer": "#/props/pageProps/schemaFileString",
                                "assertions": [{"pointer": "#/props/pageProps/releaseStage", "value": "stable"}]}}


def page(document=None, stage="stable"):
    original = document or {"openapi": "3.0.0", "info": {"title": "Original <API> & values", "version": "1.0"},
                            "paths": {"/items": {"get": {"responses": {"200": {"description": "OK"}}}}}}
    native = json.dumps(original, indent=2, ensure_ascii=False)
    data = {"props": {"pageProps": {"releaseStage": stage, "schemaFileString": native}}}
    raw = ('<html><script>throw new Error("must never execute")</script><script id="__NEXT_DATA__" '
           'type="application/json">' + json.dumps(data, ensure_ascii=False) + '</script></html>').encode()
    return raw, native.encode(), data


def fetched(raw):
    return {"url": SOURCE["url"], "sha256": update.sha256(raw), "revision": None, "fetched_at": "today"}


class EmbeddedTests(unittest.TestCase):
    def test_exact_native_string_and_original_html_are_retained_with_provenance(self):
        raw, native, _ = page()
        metadata = fetched(raw)
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            update.cache_snapshot(cache, SOURCE["id"], raw, metadata)
            spec, steps = update.prepare_document(SOURCE, raw, metadata, cache)
            metadata["transformations"] = steps
            update.cache_snapshot(cache, SOURCE["id"], raw, metadata)
            workspace = cache / SOURCE["id"] / metadata["sha256"]
            self.assertEqual((workspace / "source").read_bytes(), raw)
            self.assertEqual((workspace / "embedded-document.json").read_bytes(), native)
            self.assertEqual(spec, json.loads(native))
            self.assertEqual(metadata["embedded_document"]["document_sha256"], update.sha256(native))
            imported = update.import_document(SOURCE, spec, metadata, None)
            self.assertEqual(imported["info"]["x-origin"][0]["url"], SOURCE["url"])
            self.assertIn(update.sha256(raw), imported["info"]["x-conversion"][0])
            self.assertIn(update.sha256(native), " ".join(imported["info"]["x-conversion"]))
            self.assertNotIn("commit", imported["info"]["x-conversion"][0])

    def test_lifecycle_and_typed_assertion_changes_stop_before_conversion(self):
        for stage in ("beta", True, 1, None):
            raw, _, _ = page(stage=stage)
            with self.subTest(stage=stage), tempfile.TemporaryDirectory() as directory, \
                    patch.object(update.conversion, "prepare") as converter:
                with self.assertRaisesRegex(ValueError, "assertion changed"):
                    update.prepare_document(SOURCE, raw, fetched(raw), Path(directory))
                converter.assert_not_called()

    def test_missing_duplicate_wrong_type_external_and_unclosed_scripts_fail(self):
        raw, _, _ = page()
        variants = [b"<html>No original description</html>", raw + raw,
                    raw.replace(b'application/json', b'text/javascript'),
                    raw.replace(b'id="__NEXT_DATA__"', b'id="__NEXT_DATA__" src="https://vendor.example/code"'),
                    raw.replace(b'id="__NEXT_DATA__"', b'id="__NEXT_DATA__" id="other"'),
                    raw.replace(b'</script></html>', b''),
                    b'<script id="__NEXT_DATA__" type="application/json"/>']
        for value in variants:
            with self.subTest(value=value[:60]), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    embedded.prepare(SOURCE, value, fetched(value), Path(directory))

    def test_exact_json_string_required_no_fallback_to_rendered_operations(self):
        _, _, data = page()
        for value in ({"openapi": "3.0.0"}, None, "not json", '{"value": NaN}', '{"openapi":"3.0.0"}'):
            changed = copy.deepcopy(data)
            changed["props"]["pageProps"]["schemaFileString"] = value
            raw = ('<script id="__NEXT_DATA__" type="application/json">' + json.dumps(changed) + '</script>').encode()
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    embedded.prepare(SOURCE, raw, fetched(raw), Path(directory))

    def test_duplicate_keys_in_script_or_native_description_are_rejected(self):
        raw, _, _ = page()
        duplicate_script = raw.replace(b'"releaseStage": "stable"', b'"releaseStage":"beta","releaseStage":"stable"')
        _, _, data = page()
        data['props']['pageProps']['schemaFileString'] = '{"swagger":"2.0","swagger":"2.0","info":{},"paths":{}}'
        duplicate_native = ('<script id="__NEXT_DATA__" type="application/json">' + json.dumps(data) + '</script>').encode()
        for value in (duplicate_script, duplicate_native):
            with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "Duplicate key"):
                embedded.prepare(SOURCE, value, fetched(value), Path(directory))

    def test_changed_original_hash_redirect_or_unsupported_recipe_fail(self):
        raw, _, _ = page()
        for change in ({"sha256": "different"}, {"url": "https://elsewhere.example/reference"}):
            with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "URL or original HTML hash"):
                embedded.prepare(SOURCE, raw, {**fetched(raw), **change}, Path(directory))
        for change in ({"github": {}}, {"bundling": {"tool": "redocly"}}, {"code_samples": {"tool": "fern"}}):
            with tempfile.TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "Unsupported embedded"):
                embedded.prepare({**SOURCE, **change}, raw, fetched(raw), Path(directory))
        with self.assertRaisesRegex(ValueError, "fetch metadata"):
            update.prepare_document(SOURCE, raw)

    def test_failed_audit_retains_original_html_without_false_comparison(self):
        raw, _, _ = page(stage="beta")
        with tempfile.TemporaryDirectory() as directory, patch.object(update, "fetch", return_value=(raw, fetched(raw))):
            cache = Path(directory)
            result = update.audit(SOURCE, "origin/main", cache)
            self.assertEqual(result["status"], "failed")
            self.assertEqual((cache / SOURCE["id"] / update.sha256(raw) / 'source').read_bytes(), raw)
            self.assertNotIn("last_successful_comparison", result)
            self.assertNotIn("last_successful_validation", result)

    def test_json_pointer_escaped_names_and_list_indexes(self):
        data = {"a/b": [{"~key": "value"}]}
        self.assertEqual(embedded.pointer(data, "#/a~1b/0/~0key"), "value")
        for path in ("a/b", "#/a~2b", "#/a~1b/00", "#/a~1b/-1"):
            with self.assertRaises((ValueError, KeyError)):
                embedded.pointer(data, path)
