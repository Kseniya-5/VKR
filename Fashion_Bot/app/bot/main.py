import asyncio
from aiogram import Bot, Dispatcher

from app.core.config import BOT_TOKEN
from app.bot.middlewares import LoggingMiddleware
from app.bot.handlers.base import router as base_router
from app.bot.handlers.auth import router as auth_router


bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

dp.message.middleware(LoggingMiddleware())

dp.include_routers(
    base_router,
    auth_router,
)


async def main():
    print("Бот запущен в режиме polling!")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())