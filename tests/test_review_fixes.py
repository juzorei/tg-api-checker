import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from handlers import history, search
from handlers.api_check import parse_input, parse_pairs
from services.vault import Vault


class ReviewFixTests(unittest.IsolatedAsyncioTestCase):
    def test_long_prefixed_key_not_duplicated(self):
        self.assertEqual(
            parse_pairs('https://a.example/v1 sk-proj-abcdefghijklmnopqrstuvwxyz'),
            [('https://a.example/v1', 'sk-proj-abcdefghijklmnopqrstuvwxyz')],
        )

    def test_next_line_prefixed_key_not_duplicated(self):
        self.assertEqual(
            parse_pairs('https://a.example/v1\nsk-abcdefghijklmnop'),
            [('https://a.example/v1', 'sk-abcdefghijklmnop')],
        )

    def test_url_path_not_parsed_as_key(self):
        self.assertEqual(
            parse_pairs('https://api.example.com/v1/token/abcdefgh'),
            [('https://api.example.com/v1/token/abcdefgh', None)],
        )

    def test_dotted_mixed_case_key_recognized(self):
        text = (
            'https://open.bigmodel.cn/api/paas/v4\n'
            '169859478749e13a43a2c1b3d3f0bce0.Bnq1AThjKlmNopQr\n'
            'https://open.bigmodel.cn/api/paas/v4\n'
            'da8df5ba954341829f7afd05ca23a889.RrjoTsbaAbCdEfGh'
        )
        self.assertEqual(parse_pairs(text), [
            ('https://open.bigmodel.cn/api/paas/v4', '169859478749e13a43a2c1b3d3f0bce0.Bnq1AThjKlmNopQr'),
            ('https://open.bigmodel.cn/api/paas/v4', 'da8df5ba954341829f7afd05ca23a889.RrjoTsbaAbCdEfGh'),
        ])

    def test_key_first_single_pair_via_parse_input(self):
        self.assertEqual(parse_input('sk-aaa111222 https://a.example/v1'), ('https://a.example/v1', 'sk-aaa111222'))

    async def test_recheck_preserves_filter_flag(self):
        with tempfile.TemporaryDirectory() as d:
            vault = Vault(d)
            try:
                rid = vault.save(1, 'https://example.com/v1', 'fake', {'models': ['gpt-4'], 'results': [], 'filter_disabled': True})
                with patch('handlers.history.vault', return_value=vault), patch('handlers.history.check', AsyncMock(return_value={'models': ['gpt-4'], 'results': [], 'provider': 't'})):
                    await history.execute(1, 'https://example.com/v1', 'fake')
                self.assertTrue(vault.get(1, rid)['result']['filter_disabled'])
            finally:
                vault.db.close()

    async def test_start_batch_rejects_over_50(self):
        message = SimpleNamespace(reply=AsyncMock(), answer=AsyncMock())
        pairs = [(f'https://x{i}.example/v1', f'sk-{i:08d}') for i in range(51)]
        with patch('handlers.history.execute', AsyncMock(return_value=1)):
            await history.start_batch(message, 1, pairs)
        message.answer.assert_awaited()
        message.reply.assert_not_awaited()
        self.assertNotIn(1, history.batches)

    async def test_search_check_respects_filter_flag(self):
        store = Mock()
        record = {'id': 1, 'url': 'https://example.com', 'key': 'fake', 'result': {'models': ['gpt-4'], 'results': [], 'filter_disabled': True}}
        store.get.return_value = record
        store.jobs.return_value = [{'id': 9, 'data': {'results': []}}]
        search.sessions['tok'] = {'owner': 1, 'groups': [(1, ['gpt-4'])], 'running': False, 'stop': False}
        try:
            with patch('handlers.search.vault', return_value=store), patch('handlers.search.run', AsyncMock(return_value=9)) as run_mock, patch('handlers.search.edit', AsyncMock()):
                await search.execute(Mock(), 'tok', 1)
            self.assertFalse(run_mock.await_args.kwargs.get('use_filter', True))
        finally:
            search.sessions.clear()

    async def test_keys_list_counts_include_disabled_filter_models(self):
        store = Mock()
        store.list.return_value = [{'id': 1, 'url': 'https://e', 'key': 'sk-12345678', 'note': '', 'result': {'models': ['gpt-4', 'gpt-6'], 'results': [{'model_id': 'gpt-4', 'ok': True}, {'model_id': 'gpt-6', 'ok': True}], 'filter_disabled': True}}]
        message = SimpleNamespace(answer=AsyncMock())
        with patch('handlers.history.vault', return_value=store):
            await history.show_list(message, 1, 0, send=True)
        self.assertIn('2/2', message.answer.await_args.args[0])

    async def test_export_includes_disabled_filter_models(self):
        store = Mock()
        record = {'result': {'models': ['gpt-4', 'gpt-6'], 'results': [{'model_id': 'gpt-4', 'ok': True}, {'model_id': 'gpt-6', 'ok': True}], 'filter_disabled': True}, 'url': 'https://e', 'key': 'fake'}
        store.get.return_value = record
        call = SimpleNamespace(from_user=SimpleNamespace(id=1), data='h:export:1', answer=AsyncMock(), message=Mock(answer_document=AsyncMock()))
        with patch('handlers.history.vault', return_value=store):
            await history.callback(call)
        payload = call.message.answer_document.await_args.args[0]
        self.assertIn(b'gpt-4', payload.data)
        self.assertIn(b'gpt-6', payload.data)

    async def test_collect_switches_to_batch_on_multi_pair(self):
        message = SimpleNamespace(text='https://a.example/v1 sk-aaa111222\nhttps://b.example/v1 sk-bbb333444', from_user=SimpleNamespace(id=1), answer=AsyncMock())
        history.batches[1] = {'message': Mock(), 'items': [], 'running': False, 'cancel': False, 'ids': []}
        try:
            with patch('handlers.history.start_batch', AsyncMock()) as start:
                await history.collect(message)
            start.assert_awaited_once()
            self.assertNotIn(1, history.batches)
        finally:
            history.batches.pop(1, None)
