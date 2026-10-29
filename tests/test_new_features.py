import tempfile
import unittest
from unittest.mock import patch, AsyncMock
from services.vault import Vault
from services.jobs import run, active
from services.model_tester import ModelTestResult
from handlers.search import matches
from services.protocols import request_spec, response_text


class Features(unittest.IsolatedAsyncioTestCase):
    def test_search_version(self):
        self.assertTrue(matches('opus 5.5', 'anthropic/claude-opus-5_5'))
        self.assertFalse(matches('opus 5.5', 'opus-5.50'))

    def test_protocols(self):
        self.assertTrue(request_spec('https://example.com/v1','key','m','responses')[0].endswith('/responses'))
        self.assertEqual(response_text({'output':[{'type':'message','content':[{'type':'output_text','text':'OK'}]}]},'responses'),'OK')
        self.assertEqual(response_text({'content':[{'type':'text','text':'OK'}]},'anthropic'),'OK')

    async def test_partial_saved_and_resume(self):
        with tempfile.TemporaryDirectory() as d:
            v=Vault(d)
            rid=v.save(1,'https://example.com/v1','fake',{'models':['a','b'],'results':[], 'provider':'test'})
            async def probe(url,key,models,count,protocol='chat'):
                return [ModelTestResult(models[0],True,200,'',protocol)]
            async def progress(done,total):
                if done:
                    active[(1,rid)].set()
            with patch('services.jobs.test_models',side_effect=probe), patch('services.jobs.MAX_CONCURRENT_TESTS',1):
                await run(v,1,rid,['a','b'],'chat',progress)
                job=v.jobs(1,rid)[0]
                self.assertEqual(len(job['data']['results']),1)
                self.assertEqual(job['state'],'stopped')
                await run(v,1,rid,[],'chat',AsyncMock(),job)
            self.assertEqual(len(v.get(1,rid)['result']['results']),2)
            v.db.close()
