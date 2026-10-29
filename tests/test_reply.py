import unittest
from unittest.mock import AsyncMock, Mock, patch
from handlers.history import single


class ReplyTests(unittest.IsolatedAsyncioTestCase):
    async def test_report_edits_reply_to_key_message(self):
        message = Mock()
        progress = Mock()
        message.reply = AsyncMock(return_value=progress)
        message.answer = AsyncMock()
        with patch('handlers.history.execute', AsyncMock(return_value=7)), patch('handlers.history.vault') as storage, patch('handlers.history.report', return_value='report'), patch('handlers.history.edit', AsyncMock()) as edit:
            storage.return_value.get.return_value = {}
            await single(message, 123, 'https://example.com/v1', 'fake-key')
            message.reply.assert_awaited_once_with('⏳ Проверяю…')
            message.answer.assert_not_awaited()
            self.assertIs(edit.await_args.args[0], progress)
            self.assertEqual(edit.await_args.args[1], 'report')
