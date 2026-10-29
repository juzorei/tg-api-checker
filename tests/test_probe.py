import asyncio
import unittest
import httpx
from services.model_tester import _test_one


class ProbeTests(unittest.IsolatedAsyncioTestCase):
    async def probe(self, response):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: response)) as client:
            return await _test_one(client, asyncio.Semaphore(1), 'https://example.com/v1', 'secret-test-key', 'm')

    async def test_empty_200_rejected(self):
        result = await self.probe(httpx.Response(200, json={'choices': []}))
        self.assertFalse(result.ok)
        self.assertTrue(result.error_msg)

    async def test_text_200_accepted(self):
        result = await self.probe(httpx.Response(200, json={'choices': [{'message': {'content': 'Hi'}}]}))
        self.assertTrue(result.ok)

    async def test_error_key_redacted(self):
        result = await self.probe(httpx.Response(429, json={'error': {'message': 'quota exhausted secret-test-key', 'code': 'insufficient_quota'}}))
        self.assertIn('insufficient_quota', result.error_msg)
        self.assertNotIn('secret-test-key', result.error_msg)
