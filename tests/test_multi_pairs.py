import unittest
from handlers.api_check import parse_pairs


class MultiPairTests(unittest.TestCase):
    def test_screenshot_format_two_pairs(self):
        text = (
            'https://open.bigmodel.cn/api/paas/v4\n'
            '169859478749e13a43a2c1b3d3f0bce0\n'
            'https://open.bigmodel.cn/api/paas/v4\n'
            'da8df5ba954341829f7afd05ca23a889'
        )
        self.assertEqual(parse_pairs(text), [
            ('https://open.bigmodel.cn/api/paas/v4', '169859478749e13a43a2c1b3d3f0bce0'),
            ('https://open.bigmodel.cn/api/paas/v4', 'da8df5ba954341829f7afd05ca23a889'),
        ])

    def test_same_line_pairs(self):
        text = 'https://a.example/v1 sk-aaa111222\nhttps://b.example/v1 sk-bbb333444'
        self.assertEqual(parse_pairs(text), [
            ('https://a.example/v1', 'sk-aaa111222'),
            ('https://b.example/v1', 'sk-bbb333444'),
        ])

    def test_single_pair(self):
        self.assertEqual(parse_pairs('https://a.example/v1 sk-aaa111222'), [('https://a.example/v1', 'sk-aaa111222')])

    def test_url_only_returns_none_key(self):
        self.assertEqual(parse_pairs('https://a.example/v1'), [('https://a.example/v1', None)])

    def test_key_only_returns_empty(self):
        self.assertEqual(parse_pairs('Authorization: Bearer opaque123456'), [])

    def test_mismatch_raises(self):
        with self.assertRaises(ValueError):
            parse_pairs('https://a.example/v1\nhttps://b.example/v1\nsk-aaa111222')

    def test_duplicate_pairs_collapse(self):
        text = 'https://a.example/v1 sk-aaa111222\nhttps://a.example/v1 sk-aaa111222'
        self.assertEqual(parse_pairs(text), [('https://a.example/v1', 'sk-aaa111222')])
