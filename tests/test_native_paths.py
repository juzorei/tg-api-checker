import unittest
import httpx
from aiogram.exceptions import TelegramNetworkError
from handlers import history
from services.protocol_detect import native_catalog


class NativePathTests(unittest.IsolatedAsyncioTestCase):
    async def test_gemini_catalog_with_v1beta_base(self):
        def respond(request):
            url = str(request.url)
            if url == 'https://generativelanguage.googleapis.com/v1beta/models':
                return httpx.Response(200, json={'models': [{'name': 'models/gemini-4-argon'}]})
            return httpx.Response(404)
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            models, error = await native_catalog(client, 'https://generativelanguage.googleapis.com/v1beta', 'fake')
        self.assertEqual(models, ['gemini-4-argon'])
        self.assertIsNone(error)

    async def test_gemini_catalog_without_suffix(self):
        def respond(request):
            if str(request.url) == 'https://generativelanguage.googleapis.com/v1beta/models':
                return httpx.Response(200, json={'models': [{'name': 'models/gemini-4-argon'}]})
            return httpx.Response(404)
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            models, _ = await native_catalog(client, 'https://generativelanguage.googleapis.com', 'fake')
        self.assertEqual(models, ['gemini-4-argon'])

    async def test_anthropic_catalog_with_v1_base(self):
        def respond(request):
            if str(request.url) == 'https://api.anthropic.com/v1/models':
                return httpx.Response(200, json={'data': [{'id': 'claude-opus-5.5'}]})
            return httpx.Response(404)
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            models, _ = await native_catalog(client, 'https://api.anthropic.com/v1', 'fake')
        self.assertEqual(models, ['claude-opus-5.5'])

    async def test_cancel_sets_flag_even_if_telegram_answer_fails(self):
        class AnswerFails:
            async def answer(self):
                raise TelegramNetworkError(method=None, message='network down')
        call = type('Call', (), {})()
        call.from_user = type('U', (), {'id': 1})()
        call.data = 'h:cancel:0'
        call.answer = AnswerFails().answer
        from unittest.mock import AsyncMock
        call.message = type('M', (), {'message_id': 7, 'edit_text': AsyncMock()})()
        history.batches[1] = {'message': call.message, 'items': [('https://a.example/v1', 'sk-aaa111222')], 'running': True, 'cancel': False, 'ids': []}
        try:
            await history.callback(call)
            self.assertTrue(history.batches[1]['cancel'])
        finally:
            history.batches.pop(1, None)
