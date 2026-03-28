import asyncio
from aiogram import Bot, Dispatcher
from middlewares import LoggingMiddleware

from handlers import router
from config import BOT_TOKEN
from web_app import start_web_server

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
dp.message.middleware(LoggingMiddleware())
dp.include_router(router)

async def main():
    # Запускаем веб-сервер фоном
    asyncio.create_task(start_web_server())

    print('Бот запущен!')
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
