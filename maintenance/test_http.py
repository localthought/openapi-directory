import json
import unittest
import urllib.error
import urllib.request
from unittest.mock import MagicMock, patch

import update


class HttpTests(unittest.TestCase):
    def fetch(self, url, token="test-only-placeholder"):
        response = MagicMock()
        response.url = url
        response.headers = {"ETag": "test-etag"}
        response.read.return_value = b"public source bytes"
        response.__enter__.return_value = response
        with patch.dict(update.os.environ, {"GITHUB_TOKEN": token}), \
                patch.object(update.urllib.request, "urlopen", return_value=response) as opened:
            raw, metadata = update.request(url)
        opened.assert_called_once()
        self.assertEqual(opened.call_args.kwargs, {"timeout": 30})
        self.assertEqual(raw, b"public source bytes")
        self.assertEqual(metadata, {"url": url, "etag": "test-etag", "last_modified": None})
        return opened.call_args.args[0], metadata

    def test_github_api_authentication_is_optional_and_not_cached(self):
        for url in ("https://api.github.com/repos/vendor/spec",
                    "https://api.github.com:443/repos/vendor/spec"):
            with self.subTest(url=url):
                req, metadata = self.fetch(url)
                self.assertEqual(req.get_header("Authorization"), "Bearer test-only-placeholder")
                self.assertNotIn("Authorization", req.headers)
                self.assertNotIn("test-only-placeholder", json.dumps(metadata))
                anonymous, _ = self.fetch(url, token="")
                self.assertIsNone(anonymous.get_header("Authorization"))

    def test_token_is_never_sent_to_other_hosts_or_authorities(self):
        urls = (
            "https://vendor.example/openapi.json",
            "https://raw.githubusercontent.com/vendor/spec/main/openapi.json",
            "https://codeload.github.com/vendor/spec/tar.gz/main",
            "https://api.github.com.evil.example/spec",
            "https://api.github.com@evil.example/spec",
            "https://name@api.github.com/spec",
            "https://name:password@api.github.com/spec",
            "https://api.github.com:444/spec",
        )
        for url in urls:
            with self.subTest(url=url):
                req, _ = self.fetch(url)
                self.assertIsNone(req.get_header("Authorization"))

    def test_redirects_drop_authentication_including_same_origin(self):
        req, _ = self.fetch("https://api.github.com/repos/old/spec")
        handler = urllib.request.HTTPRedirectHandler()
        for target in ("https://api.github.com/repos/new/spec",
                       "https://vendor.example/spec", "http://vendor.example/spec"):
            with self.subTest(target=target):
                redirected = handler.redirect_request(req, None, 302, "Found", {}, target)
                self.assertIsNone(redirected.get_header("Authorization"))
                self.assertEqual(redirected.get_header("User-agent"), "ontola-openapi-maintenance")

    def test_forbidden_requests_fail_without_retry_or_anonymous_fallback(self):
        url = "https://api.github.com/repos/vendor/spec"
        error = urllib.error.HTTPError(url, 403, "rate limit exceeded", {}, None)
        with patch.dict(update.os.environ, {"GITHUB_TOKEN": "test-only-placeholder"}), \
                patch.object(update.urllib.request, "urlopen", side_effect=error) as opened, \
                patch.object(update.time, "sleep") as slept:
            with self.assertRaises(urllib.error.HTTPError) as raised:
                update.request(url)
        self.assertIs(raised.exception, error)
        opened.assert_called_once()
        slept.assert_not_called()


if __name__ == "__main__":
    unittest.main()
