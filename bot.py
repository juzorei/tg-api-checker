import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from handlers.api_check import router as api_router
from handlers.history import router as history_router, vault
from handlers.search import router as search_router


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher(storage=MemoryStorage())
    from aiogram import BaseMiddleware
    from config import ALLOWED_USER_IDS
    class AccessMiddleware(BaseMiddleware):
        async def __call__(self, handler, event, data):
            user = data.get('event_from_user')
            if ALLOWED_USER_IDS and (not user or user.id not in ALLOWED_USER_IDS):
                return
            return await handler(event, data)
    dp.update.outer_middleware(AccessMiddleware())
    vault()
    dp.include_router(search_router)
    dp.include_router(history_router)
    dp.include_router(api_router)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
