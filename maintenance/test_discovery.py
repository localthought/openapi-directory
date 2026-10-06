import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import discovery
import health
import update

REVISION, TREE = 'a' * 40, 'b' * 40
ENTRY = {"id": "vendor-catalog", "provider": "example.com", "repository": "Vendor/specs", "ref": "main",
         "patterns": ["specs/*"], "context_paths": ["README.md"], "max_candidates": 8, "max_blob_bytes": 10000,
         "ownership_evidence": "Reviewed official vendor docs link Vendor/specs.", "review_scope": "Each service needs lifecycle/scope review."}


def spec(title="API", version="1.0", path="/items"):
    return {"openapi": "3.0.3", "info": {"title": title, "version": version},
            "paths": {path: {"get": {"responses": {"200": {"description": "OK"}}}}}}


class Remote:
    def __init__(self, files, **repository_changes):
        self.files = {p: (v if isinstance(v, bytes) else json.dumps(v).encode()) for p, v in files.items()}
        self.repo = {"full_name": "Vendor/specs", "owner": {"login": "Vendor"}, "private": False,
                     "archived": False, "disabled": False, "fork": False, "default_branch": "main", **repository_changes}
        self.tree = {"sha": TREE, "truncated": False, "tree": [{"path": p, "type": "blob", "mode": "100644",
                     "size": len(raw), "sha": hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()}
                     for p, raw in self.files.items()]}
        self.calls = []
        self.fail = None

    def __call__(self, url):
        self.calls.append(url)
        if self.fail:
            raise self.fail
        if url.endswith('/repos/Vendor/specs'):
            value = json.dumps(self.repo).encode()
        elif '/commits/' in url:
            value = json.dumps({"sha": REVISION, "commit": {"tree": {"sha": TREE}}}).encode()
        elif '/git/trees/' in url:
            value = json.dumps(self.tree).encode()
        else:
            prefix = 'https://raw.githubusercontent.com/Vendor/specs/' + REVISION + '/'
            assert url.startswith(prefix), url
            value = self.files[url[len(prefix):]]
        return value, {"url": url, "etag": "fixture"}


class DiscoveryTests(unittest.TestCase):
    def scan(self, remote, cache, entry=None, registered=(), stored=()):
        return discovery.scan(entry or ENTRY, registered, stored, remote, lambda: "now", cache,
                              health.Checker(remote, lambda: "now", cache))

    def test_pinned_catalog_excludes_registered_helpers_and_exact_stored_descriptions(self):
        duplicate = spec("Stored")
        remote = Remote({"README.md": b"Official catalog", "specs/registered.yaml": spec("Registered"),
                         "specs/common.yaml": {"components": {"schemas": {"Helper": {"type": "string"}}}},
                         "specs/stored.json": duplicate, "specs/new.json": spec(path="/new")})
        registered = [{"id": "registered", "github": {"repository": "vendor/SPECS", "path": "specs/registered.yaml"}}]
        with tempfile.TemporaryDirectory() as d:
            row = self.scan(remote, Path(d), registered=registered, stored=[("APIs/example.com/1.0/openapi.yaml", duplicate)])
            self.assertEqual(row["status"], "scanned")
            self.assertEqual(row["revision"], REVISION)
            self.assertIn('https://api.github.com/repos/Vendor/specs/git/trees/' + TREE + '?recursive=1', remote.calls)
            statuses = {a["path"]: a["status"] for a in row["artifacts"]}
            self.assertEqual(statuses, {"specs/registered.yaml": "already_registered", "specs/common.yaml": "not_openapi",
                                       "specs/stored.json": "already_stored", "specs/new.json": "review_candidate"})
            self.assertFalse(any(u.endswith('specs/registered.yaml') for u in remote.calls))
            q = discovery.queue([row]); self.assertEqual(len(q), 1)
            self.assertEqual(q[0]["stats"]["paths"], 1)
            self.assertEqual(q[0]["validation_errors"], [])
            source = q[0]["sources"][0]
            self.assertIn(REVISION, source["source_url"])
            self.assertEqual((Path(source["snapshot"]) / 'source').read_bytes(), remote.files["specs/new.json"])
            self.assertEqual(source["sha256"], update.sha256(remote.files["specs/new.json"]))
            self.assertEqual(row["contexts"][0]["status"], "fetched")
            self.assertEqual(row["last_successful_scan"], "now")

    def test_submodule_contents_are_reported_as_unscanned_not_absent(self):
        remote = Remote({'README.md': b'README'})
        remote.tree['tree'].append({'path': 'specs/submodule', 'type': 'commit', 'mode': '160000', 'sha': 'c' * 40})
        with tempfile.TemporaryDirectory() as d:
            row = self.scan(remote, Path(d))
        self.assertEqual(row['status'], 'scanned')
        self.assertEqual(row['submodule_paths_not_scanned'], ['specs/submodule'])
        text = discovery.render({'generated_at': 'now', 'base_revision': REVISION,
                                 'repositories': [row], 'inventory_errors': [], 'queue': []})
        self.assertIn('Submodule contents not scanned: specs/submodule', text)
        self.assertIn('Pinned publication input: README', text)

    def test_identical_content_aliases_collapse_but_same_endpoints_do_not_erase_scope(self):
        remote = Remote({"README.md": b"README", "specs/a.json": spec(), "specs/alias.json": spec(),
                         "specs/other.json": spec(title="Different service")})
        with tempfile.TemporaryDirectory() as d:
            row = self.scan(remote, Path(d), stored=[("APIs/example.com/old/openapi.yaml", spec(title="Old"))])
        q = discovery.queue([row]); self.assertEqual(len(q), 2)
        self.assertEqual(sorted(len(c["sources"]) for c in q), [1, 2])
        self.assertTrue(all(c["same_endpoint_shape_as"] == ["APIs/example.com/old/openapi.yaml"] for c in q))
        self.assertTrue(all(len(c["same_endpoint_shape_candidates"]) == 1 for c in q))
        # Different vendors sharing a protocol must still have separate review entries.
        other = copy.deepcopy(row); other["provider"] = "different.com"
        combined = discovery.queue([row, other])
        self.assertEqual(len(combined), 4)
        self.assertTrue(all(len(c["same_endpoint_shape_candidates"]) == 1 for c in combined))

    def test_external_refs_and_native_defects_remain_review_obstacles_without_network_resolution(self):
        external = spec(); external['paths']['/items']['get']['responses']['200'] = {'$ref': 'common.yaml#/responses/OK'}
        invalid = spec(path="/invalid"); invalid['paths']['/invalid']['get']['parameters'] = [
            {'name': 'q', 'in': 'query', 'schema': {'type': 'string', 'default': None}}]
        remote = Remote({"README.md": b"README", "specs/ext.json": external, "specs/bad.json": invalid})
        with tempfile.TemporaryDirectory() as d:
            row = self.scan(remote, Path(d))
        self.assertEqual(row["status"], "scanned")  # Discovery succeeds; import approval is separate.
        q = discovery.queue([row]); self.assertEqual(len(q), 2)
        self.assertTrue(all(c['validation_errors'] for c in q))
        self.assertEqual(q[1]['external_refs'], ['common.yaml'])
        self.assertFalse(any(u.endswith('common.yaml') for u in remote.calls))

    def test_truncated_mismatched_or_over_limit_trees_never_claim_success_or_fetch_prefix(self):
        for defect in ("truncated", "identity", "limit", "unsafe-path"):
            remote = Remote({"README.md": b"README", "specs/a.json": spec()})
            entry = copy.deepcopy(ENTRY)
            if defect == 'truncated': remote.tree['truncated'] = True
            elif defect == 'identity': remote.tree['sha'] = 'c' * 40
            elif defect == 'unsafe-path': remote.tree['tree'][0]['path'] = '../escape'
            else:
                entry['max_candidates'] = 1
                remote.tree['tree'].append({**remote.tree['tree'][1], 'path': 'specs/b.json'})
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as d:
                row = self.scan(remote, Path(d), entry=entry)
                self.assertEqual(row['status'], 'failed')
                self.assertTrue(row['errors'])
                self.assertNotIn('last_successful_scan', row)
                self.assertFalse(any('raw.githubusercontent' in u for u in remote.calls))
                self.assertEqual(row['artifacts'], [])

    def test_archived_redirected_and_failed_repositories_do_not_become_absence_results(self):
        for changes in ({'archived': True}, {'disabled': True}, {'full_name': 'Other/specs', 'owner': {'login': 'Other'}}, {'private': True}):
            remote = Remote({}, **changes)
            with self.subTest(changes=changes), tempfile.TemporaryDirectory() as d:
                row = self.scan(remote, Path(d))
                self.assertEqual(row['status'], 'failed')
                self.assertTrue(row['errors'])
                self.assertEqual(len(remote.calls), 1)
                self.assertNotIn('last_successful_scan', row)

    def test_blob_identity_size_and_symlinks_fail_inspection_instead_of_silent_skips(self):
        for defect in ('hash', 'size', 'symlink', 'bad-json'):
            remote = Remote({'README.md': b'README', 'specs/a.json': spec()})
            blob = remote.tree['tree'][1]
            if defect == 'hash': remote.files['specs/a.json'] = remote.files['specs/a.json'].replace(b'API', b'BAD')
            elif defect == 'size': blob['size'] += 1
            elif defect == 'symlink': blob['mode'] = '120000'
            else:
                remote = Remote({'README.md': b'README', 'specs/a.json': b'{bad json'})
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as d:
                row = self.scan(remote, Path(d))
                self.assertEqual(row['status'], 'partial')
                self.assertEqual(row['artifacts'][0]['status'], 'inspection_failed')
                self.assertTrue(row['errors'])
                self.assertNotIn('last_successful_scan', row)

    def test_full_git_inventory_is_used_even_when_provider_is_outside_sparse_checkout(self):
        calls = []
        def git(*args):
            calls.append(args)
            if args[0] == 'rev-parse': return REVISION.encode()
            if args[0] == 'ls-tree': return b'APIs/example.com/1.0/openapi.yaml\nAPIs/elsewhere.com/1/swagger.yaml\n'
            if args[-1].endswith(':maintenance/sources.json'): return b'{"sources": []}'
            return json.dumps(spec()).encode()
        with patch.object(update, 'git', side_effect=git):
            revision, files, specs, errors, registered = discovery.inventory('origin/main', [ENTRY])
        self.assertEqual(revision, REVISION)
        self.assertEqual(len(files), 2)
        self.assertEqual(len(specs), 1)
        self.assertEqual(errors, [])
        self.assertIn(('show', REVISION + ':APIs/example.com/1.0/openapi.yaml'), calls)

    def test_failed_scan_retains_real_success_date_and_renders_failure_and_current_queue(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); config = root/'config.json'; target = root/'report.json'
            config.write_text(json.dumps({'schema_version': 1, 'repositories': [ENTRY]}))
            base = (REVISION, [], [], [], [])
            remote = Remote({'README.md': b'README', 'specs/a.json': spec()})
            with patch.object(discovery, 'inventory', return_value=base), patch.object(update, 'request', side_effect=remote), patch.object(update, 'now', return_value='yesterday'):
                self.assertEqual(discovery.main(['--config', str(config), '--cache', str(root/'cache'), '--report', str(target)]), 0)
            remote.fail = OSError('network unavailable')
            with patch.object(discovery, 'inventory', return_value=base), patch.object(update, 'request', side_effect=remote), patch.object(update, 'now', return_value='today'):
                self.assertEqual(discovery.main(['--config', str(config), '--cache', str(root/'cache'), '--report', str(target)]), 1)
            doc = json.loads(target.read_text()); row = doc['repositories'][0]
            self.assertEqual(row['checked_at'], 'today')
            self.assertEqual(row['last_successful_scan'], 'yesterday')
            self.assertIs(row['successful_scan_retained_from_previous_report'], True)
            self.assertEqual(doc['queue'], [])
            text = target.with_suffix('.md').read_text()
            self.assertIn('failed', text); self.assertIn('network unavailable', text)
            self.assertIn('proof of absence elsewhere', text)
            self.assertEqual(len(list((root/'cache'/'reports').glob('*/source'))), 2)
            self.assertFalse(list(root.glob('APIs/**/*')))

    def test_config_rejects_unreviewed_or_unsafe_expansion(self):
        for change in ('duplicate', 'unknown', 'traversal', 'zero-limit', 'bool-limit', 'missing-evidence'):
            value = {'schema_version': 1, 'repositories': [copy.deepcopy(ENTRY)]}; item = value['repositories'][0]
            if change == 'duplicate': value['repositories'].append(copy.deepcopy(ENTRY))
            elif change == 'unknown': item['import'] = True
            elif change == 'traversal': item['context_paths'] = ['../outside']
            elif change == 'zero-limit': item['max_candidates'] = 0
            elif change == 'bool-limit': item['max_blob_bytes'] = True
            else: item['ownership_evidence'] = ''
            with self.subTest(change=change), tempfile.TemporaryDirectory() as d:
                p = Path(d)/'config.json'; p.write_text(json.dumps(value))
                with self.assertRaises(ValueError): discovery.load_config(p)


if __name__ == '__main__':
    unittest.main()
