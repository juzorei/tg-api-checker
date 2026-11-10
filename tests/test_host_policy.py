import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from handlers import history
from services.host_policy import non_llm_reason


class HostPolicyTests(unittest.IsolatedAsyncioTestCase):
    def test_known_non_llm_hosts(self):
        for url, needle in [
            ('https://api.stripe.com/v1', 'Stripe'),
            ('https://api.github.com', 'GitHub'),
            ('https://api.telegram.org', 'Telegram'),
        ]:
            with self.subTest(url=url):
                self.assertIn(needle, non_llm_reason(url) or '')

    def test_trailing_dot_host_still_blocked(self):
        self.assertIn('Stripe', non_llm_reason('https://api.stripe.com./v1') or '')

    def test_huggingface_router_allowed(self):
        self.assertIsNone(non_llm_reason('https://router.huggingface.co/v1'))
        self.assertIn('Hugging Face', non_llm_reason('https://api-inference.huggingface.co/models') or '')

    def test_llm_hosts_allowed(self):
        for url in ['https://api.openai.com/v1', 'https://api.anthropic.com/v1', 'https://generativelanguage.googleapis.com/v1beta', 'https://my-gateway.example/v1']:
            with self.subTest(url=url):
                self.assertIsNone(non_llm_reason(url))

    async def test_single_refuses_and_does_not_save(self):
        message = SimpleNamespace(reply=AsyncMock())
        with patch('handlers.history.check', AsyncMock()) as check_mock, patch('handlers.history.vault') as vault_mock:
            await history.single(message, 1, 'https://api.stripe.com/v1', 'sk_live_test')
        check_mock.assert_not_awaited()
        vault_mock.return_value.save.assert_not_called()
        text = message.reply.await_args.args[0]
        self.assertIn('Stripe', text)
        self.assertIn('не сохранён', text)

    async def test_batch_skips_non_llm_and_continues(self):
        message = Mock()
        message.edit_text = AsyncMock()
        message.answer = AsyncMock()
        batch = {'message': message, 'items': [('https://api.stripe.com/v1', 'sk_live_test'), ('https://ok.example/v1', 'sk-ok123456')], 'running': False, 'cancel': False, 'ids': []}
        with patch('handlers.history.execute', AsyncMock(return_value=5)) as execute_mock, patch('handlers.history.show_list', AsyncMock()) as show_mock:
            await history.run_batch(message, 1, batch)
        execute_mock.assert_awaited_once()
        self.assertEqual(execute_mock.await_args.args[1], 'https://ok.example/v1')
        show_mock.assert_awaited_once()
        self.assertEqual(batch['ids'], [5])
