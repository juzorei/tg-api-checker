import unittest
from services.formatters import format_check_result
from services.model_tester import ModelTestResult


class ErrorSummaryTests(unittest.TestCase):
    def test_repeated_errors_grouped(self):
        rows = [ModelTestResult(str(i), False, 423, 'Too many concurrent requests') for i in range(18)]
        text = format_check_result('API', '', 'secret', 'https://example.com/v1', 18, rows)
        self.assertEqual(text.count('Too many concurrent requests'), 1)
        self.assertIn('18 × HTTP 423', text)

    def test_error_escaped_and_redacted(self):
        rows = [ModelTestResult('x', False, 400, '<bad> secret')]
        text = format_check_result('API', '', 'secret', 'https://example.com/v1', 1, rows)
        self.assertIn('&lt;bad&gt; [ключ скрыт]', text)
