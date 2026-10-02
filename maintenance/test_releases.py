import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import releases
import update
from test_update import document


def config():
    return {"repository": "vendor/api", "ref": "main", "path": "descriptions/2.16/api.yaml",
            "release_catalog": {"kind": "numeric-directories", "directory": "descriptions",
                                "filename": "api.yaml", "minimum_version": "2.16"}}


def catalog(names):
    return [{"name": name, "path": "descriptions/" + name, "type": "dir"} for name in names]


class ReleaseTests(unittest.TestCase):
    def test_numeric_selection_ignores_preview_and_lexical_order(self):
        entries = catalog(["0", "2.9", "2.16", "2.17-preview", "2.18", "2.100", "2.0101"])
        entries.append({"name": "3.0", "type": "file"})
        raw = json.dumps(entries).encode()
        def request(url):
            self.assertEqual(url, "https://api.github.com/repos/vendor/api/contents/descriptions?ref=" + "a" * 40)
            return raw, {}
        path, metadata = releases.select(config(), "a" * 40, request)
        self.assertEqual(path, "descriptions/2.100/api.yaml")
        self.assertEqual(metadata["selected_version"], "2.100")
        self.assertEqual(metadata["sha256"], update.sha256(raw))
        self.assertEqual(metadata["response_text"].encode(), raw)

    def test_catalog_failure_does_not_fall_back_to_old_url(self):
        for entries in (catalog(["2.15", "2.17-beta", "0"]), {"message": "Not found"},
                        catalog(["2.16"]) * 1000,
                        [{"name": "2.16", "path": "other/2.16", "type": "dir"}],
                        catalog(["2.16", "2.16"])):
            with self.subTest(entries=str(entries)[:100]):
                with self.assertRaises(ValueError):
                    releases.select(config(), "a" * 40, lambda url: (json.dumps(entries).encode(), {}))

    def test_unsafe_configuration_is_rejected_before_network(self):
        for key, value in (("directory", "../escape"), ("directory", "/absolute"),
                           ("filename", "../api.yaml"), ("filename", "api.yaml?raw=1"),
                           ("minimum_version", "2.16-preview"), ("minimum_version", "02.16")):
            cfg = config()
            cfg["release_catalog"][key] = value
            with self.subTest(key=key, value=value):
                with self.assertRaises(ValueError):
                    releases.select(cfg, "a" * 40, lambda url: self.fail("Unexpected network access"))

    def test_catalog_network_failure_blocks_fetch_without_requesting_fallback(self):
        calls = []
        def request(url):
            calls.append(url)
            if "/commits/" in url:
                return json.dumps({"sha": "a" * 40}).encode(), {}
            if "/contents/" in url:
                raise OSError("Catalog unavailable")
            self.fail("Fallback artifact must not be requested")
        with patch.object(update, "request", side_effect=request):
            with self.assertRaisesRegex(OSError, "Catalog unavailable"):
                update.fetch({"github": config()})
        self.assertEqual(len(calls), 2)

    def test_fetch_pins_catalog_and_artifact_to_same_revision_and_caches_evidence(self):
        revision = "a" * 40
        calls = []
        raw = json.dumps(document("2.17")).encode()
        catalog_raw = json.dumps(catalog(["2.16", "2.17"]), indent=2).encode()
        def request(url):
            calls.append(url)
            if "/commits/" in url:
                return json.dumps({"sha": revision}).encode(), {}
            if "/contents/" in url:
                self.assertTrue(url.endswith("?ref=" + revision))
                return catalog_raw, {}
            self.assertEqual(url, "https://raw.githubusercontent.com/vendor/api/" + revision + "/descriptions/2.17/api.yaml")
            return raw, {"url": url}
        source = {"github": config()}
        with patch.object(update, "request", side_effect=request):
            fetched, metadata = update.fetch(source)
        self.assertEqual(len(calls), 3)
        self.assertEqual(metadata["revision"], revision)
        parsed, _ = update.prepare_document(source, fetched, metadata)
        self.assertEqual(parsed["info"]["version"], "2.17")
        with tempfile.TemporaryDirectory() as directory:
            update.cache_snapshot(Path(directory), "example", fetched, metadata)
            cached = Path(directory) / "example" / metadata["sha256"] / "release-catalog.json"
            self.assertEqual(cached.read_bytes(), catalog_raw)
        wrong = copy.deepcopy(metadata)
        wrong["release_catalog"]["selected_version"] = "2.18"
        with self.assertRaisesRegex(ValueError, "does not match"):
            update.prepare_document(source, fetched, wrong)
        result = update.import_document({"target": "APIs/example.com/2.16/openapi.yaml"}, parsed, metadata, None)
        self.assertIn("Selected numeric release 2.17", result["info"]["x-conversion"][1])


if __name__ == "__main__":
    unittest.main()
