import unittest
import httpx
from services.protocol_detect import detect_protocol, native_catalog


class AutoProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_openai_style_keeps_chat(self):
        def respond(request):
            path = str(request.url)
            if path.endswith('/models'):
                return httpx.Response(200, json={'data': [{'id': 'x'}]})
            if path.endswith('/chat/completions'):
                return httpx.Response(200, json={'choices': [{'message': {'content': 'OK'}}]})
            return httpx.Response(404)
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            protocol = await detect_protocol(client, 'https://example.com/v1', 'fake', 'provider/model')
        self.assertEqual(protocol, 'chat')

    async def test_404_falls_back_to_responses(self):
        def respond(request):
            path = str(request.url)
            if path.endswith('/responses'):
                return httpx.Response(200, json={'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'OK'}]}]})
            if path.endswith('/models'):
                return httpx.Response(200, json={'data': [{'id': 'x'}]})
            return httpx.Response(404, json={'error': {'message': 'Unknown route'}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            protocol = await detect_protocol(client, 'https://example.com/v1', 'fake', 'x')
        self.assertEqual(protocol, 'responses')

    async def test_auth_error_not_treated_as_protocol(self):
        state = {'calls': 0}
        def respond(request):
            state['calls'] += 1
            return httpx.Response(401, json={'error': {'message': 'bad key'}})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            protocol = await detect_protocol(client, 'https://example.com/v1', 'fake', 'x')
        self.assertEqual(protocol, 'chat')
        self.assertEqual(state['calls'], 1)

    async def test_native_catalogs(self):
        base = 'https://api.anthropic.com'
        def respond(request):
            path = str(request.url)
            if path.endswith('/v1/models') and str(request.url).startswith(base):
                return httpx.Response(200, json={'data': [{'id': 'claude-x', 'display_name': 'x'}]})
            if path.endswith('/models'):
                return httpx.Response(404)
            return httpx.Response(404)
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            models, _ = await native_catalog(client, base, 'fake')
            self.assertEqual(models, ['claude-x'])
        def respond2(request):
            if 'v1beta/models' in str(request.url):
                return httpx.Response(200, json={'models': [{'name': 'models/gemini-x'}]})
            return httpx.Response(404)
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond2)) as client:
            models, _ = await native_catalog(client, 'https://generativelanguage.googleapis.com', 'fake')
            self.assertEqual(models, ['gemini-x'])
