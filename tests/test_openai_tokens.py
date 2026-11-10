import asyncio
import json
import unittest
from unittest.mock import patch
import httpx
from services.model_policy import select_models
from services.model_tester import _test_one


class OpenAITokenParamTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_with_max_completion_tokens(self):
        seen = []

        def respond(request):
            payload = json.loads(request.content)
            seen.append(payload)
            if 'max_tokens' in payload:
                return httpx.Response(400, json={'error': {'message': "Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead.", 'type': 'invalid_request_error'}})
            return httpx.Response(200, json={'choices': [{'message': {'content': 'OK'}}]})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await _test_one(client, asyncio.Semaphore(1), 'https://api.openai.com/v1', 'sk-test', 'gpt-6-astra')
        self.assertTrue(result.ok)
        self.assertEqual(len(seen), 2)
        self.assertIn('max_completion_tokens', seen[1])
        self.assertNotIn('max_tokens', seen[1])

    async def test_other_400_not_retried(self):
        calls = []

        def respond(request):
            calls.append(1)
            return httpx.Response(400, json={'error': {'message': 'bad request'}})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await _test_one(client, asyncio.Semaphore(1), 'https://api.openai.com/v1', 'sk-test', 'm')
        self.assertFalse(result.ok)
        self.assertEqual(len(calls), 1)

    async def test_retry_network_failure_keeps_original_400(self):
        calls = []

        def respond(request):
            calls.append(1)
            if len(calls) == 1:
                return httpx.Response(400, json={'error': {'message': "Unsupported parameter: 'max_tokens' is not supported with this model."}})
            raise httpx.ConnectError('boom')

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await _test_one(client, asyncio.Semaphore(1), 'https://api.openai.com/v1', 'sk-test', 'm')
        self.assertEqual(result.status_code, 400)
        self.assertIn('max_tokens', result.error_msg)

    def test_not_chat_model_label(self):
        from services.formatters import short_error
        label = short_error(404, 'This is not a chat model and thus not supported in the v1/chat/completions endpoint.')
        self.assertIn('не чат-модель', label)

    def test_realtime_models_excluded(self):
        allowed, skipped = select_models(['gpt-live-1', 'gpt-realtime-preview', 'gpt-6-astra'])
        self.assertEqual(allowed, ['gpt-6-astra'])
        self.assertIn('gpt-live-1', skipped)
        self.assertIn('gpt-realtime-preview', skipped)
