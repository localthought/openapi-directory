import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import report
import update


class ReportTests(unittest.TestCase):
    def test_blocked_match_is_not_counted_as_valid_and_removals_stay_visible(self):
        doc = {'generated_at': 'today', 'base': 'origin/main', 'base_revision': 'revision', 'sources': [
            {'id': 'good', 'status': 'matches_source', 'last_successful_validation': 'today'},
            {'id': 'archived', 'status': 'matches_source', 'source_health': 'archived',
             'import_blocker': 'Coverage uncertain', 'last_successful_validation': 'yesterday'},
            {'id': 'bad', 'status': 'changed', 'validation_errors': ['Missing schema'],
             'added_paths': ['/new'], 'removed_paths': ['/old'],
             'added_operations': ['GET /new'], 'removed_operations': ['POST /old']},
            {'id': 'offline', 'status': 'failed', 'error': 'Network unavailable'}]}
        result = report.render(doc)
        self.assertIn('1 source matches; 0 changed; 0 missing; 2 blocked; 1 failed; 0 unassessed.', result)
        self.assertIn('Paths: 1 added / 1 removed.', result)
        self.assertIn('POST /old', result)
        self.assertIn('Import blocked', result)
        self.assertIn('Coverage uncertain', result)
        self.assertIn('Missing schema', result)
        self.assertIn('Network unavailable', result)
        self.assertIn('Not recorded', result)

    def test_subset_summary_preserves_old_base_and_success_dates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'report.json'
            path.write_text(json.dumps({'sources': [
                {'id': 'updated', 'base_revision': 'old', 'status': 'matches_source',
                 'checked_at': 'yesterday', 'last_successful_validation': 'yesterday'},
                {'id': 'retained', 'base_revision': 'retained-base', 'status': 'matches_source',
                 'checked_at': 'last week', 'last_successful_validation': 'last week'}]}))
            with patch.object(update, 'git', return_value=b'new-base\n'):
                update.write_report(path, [{'id': 'updated', 'status': 'failed', 'checked_at': 'today'}], 'origin/main')
            rows = {row['id']: row for row in json.loads(path.read_text())['sources']}
            self.assertEqual(rows['updated']['base_revision'], 'new-base')
            self.assertEqual(rows['updated']['last_successful_validation'], 'yesterday')
            self.assertEqual(rows['retained']['base_revision'], 'retained-base')
            self.assertEqual(rows['retained']['checked_at'], 'last week')
            rendered = path.with_suffix('.md').read_text()
            self.assertIn('Fetch/prepare failed', rendered)
            self.assertIn('yesterday', rendered)
            self.assertIn('last week', rendered)
            self.assertIn('retained\\-base', rendered)

    def test_vendor_content_cannot_inject_markdown_rows_links_or_html(self):
        value = '<script>run()</script> | [link](https://example.com)\n# Heading `code`'
        result = report.text(value)
        self.assertNotIn('<script>', result)
        self.assertNotIn('\n', result)
        self.assertIn('\\|', result)
        self.assertIn('\\[link\\]', result)
        self.assertIn('\\# Heading', result)
        self.assertIn('\\`code\\`', result)

    def test_custom_report_name_cannot_overwrite_json_with_markdown(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'custom.md'
            with patch.object(update, 'git', return_value=b'base\n'):
                update.write_report(path, [{'id': 'one', 'status': 'failed'}], 'origin/main')
            self.assertEqual(json.loads(path.read_text())['sources'][0]['id'], 'one')
            self.assertTrue(path.with_suffix('.summary.md').read_text().startswith('# Official-source audit'))


if __name__ == '__main__':
    unittest.main()
