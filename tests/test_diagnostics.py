import unittest
import httpx
from services.diagnostics import diagnose, limits


class DiagnosticsTests(unittest.IsolatedAsyncioTestCase):
    async def test_diagnosis_does_not_claim_identity(self):
        def respond(request):
            return httpx.Response(200, json={'model': 'reported-model', 'choices': [{'message': {'content': '{"answer":42}'}, 'finish_reason': 'stop'}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            text = await diagnose(client, 'https://example.com/v1', 'secret', 'requested')
        self.assertIn('reported-model', text)
        self.assertIn('не доказывает', text)
        self.assertNotIn('100%', text)

    async def test_limits_headers(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, headers={'x-ratelimit-remaining-requests': '12'}, json={'data': []}))) as client:
            text = await limits(client, 'https://example.com/v1', 'secret')
        self.assertIn('12', text)
        self.assertIn('не раскры', text)

    async def test_http_error_not_quota_claim(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(403))) as client:
            text = await limits(client, 'https://example.com/v1', 'secret')
        self.assertIn('403', text)
        self.assertNotIn('баланс: 0', text.lower())
