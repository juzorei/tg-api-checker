import unittest
from services.formatters import format_check_result, format_models_page
from services.model_tester import ModelTestResult


class FormattingTests(unittest.TestCase):
    def test_connection_details_above_key(self):
        text = format_check_result('API', 'Unknown', 'test-key', 'https://example.com/v1', 0, [])
        self.assertLess(text.index('https://example.com/v1'), text.index('test-key'))
        self.assertIn('</code>\n🔑 Ключ:', text)
        self.assertNotIn('POST /chat/completions', text)
        self.assertEqual(text.count('https://example.com/v1'), 1)
        self.assertIn('💳 Лимиты:', text)

    def test_failed_models_hidden(self):
        rows = [ModelTestResult('good', True, 200, ''), ModelTestResult('bad', False, None, 'timeout')]
        text = format_check_result('API', 'Unknown', 'key', 'https://example.com/v1', 2, rows)
        self.assertIn('<code>good</code>', text)
        self.assertNotIn('bad', text)
        self.assertIn('1 из 2', text)

    def test_page_has_separate_code_entities(self):
        text = format_models_page('API', ['model-a', 'model<b>'], 0, 60)
        self.assertIn('<code>model-a</code>\n<code>model&lt;b&gt;</code>', text)

    def test_report_has_separate_code_entities(self):
        rows = [ModelTestResult(name, True, 200, '') for name in ['model-a', 'model-b']]
        text = format_check_result('API', 'Unknown', 'test-key', 'https://example.com/v1', 2, rows)
        self.assertIn('<code>model-a</code>\n<code>model-b</code>', text)
