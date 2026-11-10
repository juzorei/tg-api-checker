import asyncio
import unittest
from unittest.mock import AsyncMock, patch
import httpx
from services.host_policy import non_llm_reason
from services.replicate import build_input, list_models, probe_many


class ReplicateTests(unittest.IsolatedAsyncioTestCase):
    def test_build_input_from_schema(self):
        schema = {'components': {'schemas': {'Input': {
            'required': ['prompt', 'steps', 'mode'],
            'properties': {
                'prompt': {'type': 'string'},
                'steps': {'type': 'integer'},
                'mode': {'type': 'string', 'enum': ['fast', 'slow']},
                'seed': {'type': 'integer', 'default': 7},
            },
        }}}}
        self.assertEqual(build_input(schema), {'prompt': 'OK', 'steps': 1, 'mode': 'fast'})

    def test_build_input_rejects_file_inputs(self):
        schema = {'components': {'schemas': {'Input': {
            'required': ['image'],
            'properties': {'image': {'type': 'string', 'format': 'uri'}},
        }}}}
        self.assertIsNone(build_input(schema))

    def test_replicate_not_refused(self):
        self.assertIsNone(non_llm_reason('https://api.replicate.com/v1'))

    async def test_list_models_paginates(self):
        def respond(request):
            url = str(request.url)
            if 'cursor=2' in url:
                return httpx.Response(200, json={'next': None, 'results': [{'owner': 'b', 'name': 'm2', 'latest_version': {'openapi_schema': {'x': 1}}}]})
            return httpx.Response(200, json={'next': 'https://api.replicate.com/v1/models?cursor=2', 'results': [{'owner': 'a', 'name': 'm1', 'latest_version': {'openapi_schema': {'y': 2}}}]})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            models, schemas, error = await list_models(client, 'r8_test')
        self.assertIsNone(error)
        self.assertEqual(models, ['a/m1', 'b/m2'])
        self.assertEqual(schemas['a/m1'], {'y': 2})

    async def test_probe_succeeded_and_failed(self):
        def respond(request):
            url = str(request.url)
            if request.method == 'POST':
                prediction_id = 'p1' if 'a/m1' in url else 'p2'
                return httpx.Response(201, json={'id': prediction_id, 'status': 'starting'})
            if url.endswith('/p1'):
                return httpx.Response(200, json={'id': 'p1', 'status': 'succeeded'})
            return httpx.Response(200, json={'id': 'p2', 'status': 'failed', 'error': 'model crashed'})
        schema = {'components': {'schemas': {'Input': {'required': ['prompt'], 'properties': {'prompt': {'type': 'string'}}}}}}
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with patch('services.replicate.asyncio.sleep', new_callable=AsyncMock):
                results = await probe_many(client, 'r8_test', [('a/m1', schema), ('a/m2', schema)], timeout=5)
        by_id = {r.model_id: r for r in results}
        self.assertTrue(by_id['a/m1'].ok)
        self.assertFalse(by_id['a/m2'].ok)
        self.assertIn('model crashed', by_id['a/m2'].error_msg)

    async def test_probe_timeout(self):
        def respond(request):
            if request.method == 'POST':
                return httpx.Response(201, json={'id': 'p1', 'status': 'starting'})
            return httpx.Response(200, json={'id': 'p1', 'status': 'processing'})
        schema = {'components': {'schemas': {'Input': {'required': ['prompt'], 'properties': {'prompt': {'type': 'string'}}}}}}
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with patch('services.replicate.asyncio.sleep', new_callable=AsyncMock), patch('services.replicate.asyncio.get_running_loop') as loop:
                loop.return_value.time.side_effect = [0, 0, 0, 0, 10]
                results = await probe_many(client, 'r8_test', [('a/m1', schema)], timeout=5)
        self.assertFalse(results[0].ok)
        self.assertIn('Не завершилась', results[0].error_msg)
