import unittest
from services.checking import report


class FullKeyReportTests(unittest.TestCase):
    def test_key_is_complete_and_escaped(self):
        record = {'url': 'https://example.com/v1', 'key': 'sk-test-full-key<&>', 'result': {'provider': 'Example', 'models': [], 'results': []}}
        self.assertIn('<code>sk-test-full-key&lt;&amp;&gt;</code>', report(record))

    def test_failed_report_shows_full_key(self):
        record = {'url': 'https://example.com/v1', 'key': 'sk-test-full-key', 'result': {'error': 'Catalog unavailable'}}
        self.assertIn('<code>sk-test-full-key</code>', report(record))
