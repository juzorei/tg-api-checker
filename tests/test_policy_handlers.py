import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from handlers import history, search
from services.vault import Vault
from services.model_tester import ModelTestResult


class PolicyHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_omits_old_versions(self):
        store = Mock()
        store.list.return_value = [{'id':1, 'result':{'models':['gpt-4','gpt-6']}}]
        store.get.return_value = {'id':1, 'url':'https://example.com', 'updated':'now'}
        message = SimpleNamespace(text='/find gpt', from_user=SimpleNamespace(id=987), answer=AsyncMock())
        try:
            with patch('handlers.search.vault', return_value=store):
                await search.find(message)
            text = message.answer.await_args.args[0]
            self.assertIn('gpt-6', text)
            self.assertNotIn('gpt-4', text)
            self.assertIn('пропущено фильтром версий: 1', text)
        finally:
            search.sessions.clear()

    async def test_single_model_diagnostics_cannot_bypass_filter(self):
        store = Mock()
        store.get.return_value = {'result':{'models':['gpt-4']}}
        call = SimpleNamespace(from_user=SimpleNamespace(id=123), data='h:diag:1:0', answer=AsyncMock(), message=Mock())
        with patch('handlers.history.vault', return_value=store), patch('handlers.history.edit', AsyncMock()) as edit, patch('handlers.history.diagnose', AsyncMock()) as diagnose:
            await history.callback(call)
            diagnose.assert_not_awaited()
            self.assertIn('ниже 6', edit.await_args.args[1])

    async def test_recheck_samples_after_filter(self):
        store = Mock()
        store.get.return_value = {'result':{'models':['gpt-4']*20 + ['gpt-6']}, 'url':'https://example.com','key':'fake'}
        call = SimpleNamespace(from_user=SimpleNamespace(id=123), data='h:check:1', answer=AsyncMock(), message=Mock())
        with patch('handlers.history.vault', return_value=store), patch('handlers.history.edit', AsyncMock()), patch('handlers.history.report',return_value='report'), patch('services.jobs.run', AsyncMock()) as run:
            await history.callback(call)
            self.assertEqual(run.await_args.args[3], ['gpt-6'])
