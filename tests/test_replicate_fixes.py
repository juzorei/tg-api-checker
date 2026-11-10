import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
import httpx
from handlers import history
from services.formatters import short_error
from services.replicate import is_replicate_host, list_models, probe_many


class ReplicateFixTests(unittest.IsolatedAsyncioTestCase):
    def test_host_match_is_exact(self):
        self.assertTrue(is_replicate_host('https://api.replicate.com/v1'))
        self.assertTrue(is_replicate_host('https://replicate.com'))
        self.assertFalse(is_replicate_host('https://notreplicate.com/v1'))
        self.assertFalse(is_replicate_host('https://replicate.com.evil.tld/v1'))

    async def test_pagination_guard_stops_on_repeated_next(self):
        calls = []

        def respond(request):
            calls.append(1)
            return httpx.Response(200, json={'next': 'https://api.replicate.com/v1/models?cursor=1', 'results': []})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            models, _, error = await list_models(client, 'r8_test')
        self.assertEqual(models, [])
        self.assertIsNone(error)
        self.assertLessEqual(len(calls), 2)

    async def test_non_json_poll_does_not_crash(self):
        def respond(request):
            if request.method == 'POST':
                return httpx.Response(201, json={'id': 'p1', 'status': 'starting'})
            return httpx.Response(200, text='<html>oops</html>')

        schema = {'components': {'schemas': {'Input': {'required': ['prompt'], 'properties': {'prompt': {'type': 'string'}}}}}}
        clock = {'t': 0}
        async def tick(_):
            clock['t'] += 10
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with patch('services.replicate.asyncio.sleep', side_effect=tick), patch('services.replicate.asyncio.get_running_loop') as loop:
                loop.return_value.time.side_effect = lambda: clock['t']
                results = await probe_many(client, 'r8_test', [('a/m1', schema)], timeout=5)
        self.assertFalse(results[0].ok)
        self.assertIn('Не завершилась', results[0].error_msg)

    async def test_timeout_cancels_prediction(self):
        cancelled = []

        def respond(request):
            if request.method == 'POST' and request.url.path.endswith('/cancel'):
                cancelled.append(1)
                return httpx.Response(200, json={'status': 'canceled'})
            if request.method == 'POST':
                return httpx.Response(201, json={'id': 'p1', 'status': 'starting'})
            return httpx.Response(200, json={'id': 'p1', 'status': 'processing'})

        schema = {'components': {'schemas': {'Input': {'required': ['prompt'], 'properties': {'prompt': {'type': 'string'}}}}}}
        clock = {'t': 0}
        async def tick(_):
            clock['t'] += 10
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with patch('services.replicate.asyncio.sleep', side_effect=tick), patch('services.replicate.asyncio.get_running_loop') as loop:
                loop.return_value.time.side_effect = lambda: clock['t']
                await probe_many(client, 'r8_test', [('a/m1', schema)], timeout=5)
        self.assertEqual(cancelled, [1])

    def test_replicate_error_labels(self):
        self.assertEqual(short_error(None, 'model crashed', 'replicate'), 'предсказание не выполнено')
        self.assertEqual(short_error(None, 'Не завершилась за 90 с (статус processing)', 'replicate'), 'таймаут предсказания')

    async def test_recheck_uses_execute_for_replicate(self):
        store = Mock()
        record = {'result': {'models': ['a/m1'], 'results': [], 'protocol': 'replicate'}, 'url': 'https://api.replicate.com/v1', 'key': 'r8_test'}
        store.get.return_value = record
        call = SimpleNamespace(from_user=SimpleNamespace(id=1), data='h:check:1', answer=AsyncMock(), message=Mock(edit_text=AsyncMock()))
        with patch('handlers.history.vault', return_value=store), patch('handlers.history.edit', AsyncMock()), patch('handlers.history.report', return_value='r'), patch('handlers.history.execute', AsyncMock(return_value=1)) as execute_mock, patch('services.jobs.run', AsyncMock()) as run_mock:
            await history.callback(call)
        execute_mock.assert_awaited_once()
        run_mock.assert_not_awaited()
