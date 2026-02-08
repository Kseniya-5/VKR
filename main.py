import asyncio
import logging
from aiogram import Bot, Dispatcher, Router
from aiogram.types import Message
from aiogram.filters import CommandStart
from dotenv import load_dotenv
import os

load_dotenv()
logging.basicConfig(level=logging.INFO)

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer("Привет! Отправь мне фото одежды — подберу образы.")

@router.message()
async def echo(message: Message):
    if message.photo:
        await message.answer("Получил фото! Анализирую.")
    else:
        await message.answer("Я понимаю только фото одежды. Отправь изображение!")

async def main():
    bot = Bot(token=os.getenv("BOT_TOKEN"))
    dp = Dispatcher()
    dp.include_router(router)
    
    logging.info("Бот запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
