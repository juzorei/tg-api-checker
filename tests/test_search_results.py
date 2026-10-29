import unittest
from handlers.search import render_results


class SearchResultTests(unittest.TestCase):
    def test_readable_results_and_escaping(self):
        rows = [dict(rid=1, url='https://example.com/v1', model='opus<5.5>', ok=True, status=200, error=''), dict(rid=2, url='https://two.example/v1', model='opus', ok=False, status=403, error='Access <denied>')]
        text, buttons = render_results(rows, 0, 'abc', 2, False)
        self.assertIn('2/2', text)
        self.assertIn('opus&lt;5.5&gt;', text)
        self.assertIn('HTTP 403', text)
        self.assertIn('Access &lt;denied&gt;', text)
        self.assertNotIn('/keys', text)
        self.assertEqual(buttons.inline_keyboard[0][0].callback_data, 'h:view:1')

    def test_pagination(self):
        rows = [dict(rid=i, url='https://example.com', model=f'm{i}', ok=True, status=200, error='') for i in range(8)]
        text, buttons = render_results(rows, 1, 'abc', 8, False)
        self.assertIn('m5', text)
        self.assertNotIn('<code>m0</code>', text)
        self.assertTrue(any(b.callback_data == 'searchpage:abc:0' for row in buttons.inline_keyboard for b in row))
