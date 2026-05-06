import asyncio

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.handlers.base import router as base_router
from app.bot.middlewares import LoggingMiddleware
from app.core.config import BOT_TOKEN


bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

dp.message.middleware(LoggingMiddleware())
dp.callback_query.middleware(LoggingMiddleware())

# Important: only the current base router is enabled.
# Old app.bot.handlers.auth used endpoints that no longer exist and duplicated state handlers.
dp.include_routers(base_router)


async def main():
    print("Бот запущен в режиме polling!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
