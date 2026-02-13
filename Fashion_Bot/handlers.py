from aiogram import Router

router = Router()

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.reply("Добро пожаловать! Отправь мне фото одежды — подберу образы")

@router.message()
async def echo(message: Message):
    if message.photo:
        await message.answer("📸 Получил фото! Анализирую... (скоро будет подбор образов)")
    else:
        await message.answer("💬 Я понимаю только фото одежды. Отправь изображение!")

