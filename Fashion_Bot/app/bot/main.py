import asyncio
from aiogram import Bot, Dispatcher

from app.core.config import BOT_TOKEN
from app.bot.middlewares import LoggingMiddleware
from app.bot.handlers.base import router 

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

dp.message.middleware(LoggingMiddleware())
dp.include_router(router)

async def main():
    print('🤖 Бот запущен в режиме polling!')
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())