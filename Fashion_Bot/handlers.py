from aiogram import Router, types
from aiogram.filters import Command
from aiogram.types import Message
import uuid
import psycopg2
import os
from tasks import train_model_task

router = Router()

def get_db_connection():
    return psycopg2.connect(os.getenv('DATABASE_URL'))

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.reply("Добро пожаловать! Отправь мне фото одежды — подберу образы.\n"
                        "Также доступны команды:\n"
                        "/train — запустить долгую задачу\n"
                        "/status <id> — проверить статус задачи")


# Команда для постановки задачи в очередь
@router.message(Command("train"))
async def start_training(message: Message):
    task_id = str(uuid.uuid4())  # Генерируем уникальный ID задачи

    # Сохраняем задачу в БД
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO model_tasks (task_id, status) VALUES (%s, %s)",
            (task_id, 'PENDING')
        )
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        await message.answer(f"Ошибка при работе с БД: {e}")
        return

    # Отправляем задачу в очередь
    train_model_task.delay(task_id, "параметры_модели_заглушка")

    # Отвечаем пользователю
    await message.answer(
        f"Задача успешно добавлена в очередь! \n"
        f"Ваш ID задачи:\n`{task_id}`\n\n"
        f"Чтобы проверить статус, отправьте команду:\n"
        f"`/status {task_id}`",
        parse_mode="Markdown"
    )

# Команда для проверки статуса задачи
@router.message(Command("status"))
async def check_status(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("Пожалуйста, укажите ID задачи. Пример:\n`"
                             "/status 12345678-1234-5678-1234-567812345678`",
                             parse_mode="Markdown")
        return

    task_id = args[1].strip()

    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status, result FROM model_tasks WHERE task_id = %s", (task_id,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()

        if row:
            status, result = row
            if status == 'SUCCESS':
                await message.answer(f"Статус: Готово ✅\nРезультат: {result}")
            elif status == 'PROCESSING':
                await message.answer("Статус: В процессе ... Пожалуйста, подождите.")
            elif status == 'PENDING':
                await message.answer("Статус: В очереди. Скоро начнется.")
            elif status == 'FAILED':
                await message.answer(f"Статус: Ошибка ❌\nДетали: {result}")
            else:
                await message.answer(f"Статус: {status}\nРезультат: {result}")
        else:
            await message.answer("Задача с таким ID не найдена ❌.")
    except Exception as e:
        await message.answer(f"Ошибка при проверке статуса: {e}")


@router.message()
async def echo(message: Message):
    if message.photo:
        await message.answer("📸 Получил фото! Анализирую... (скоро будет подбор образов)")
    else:
        await message.answer("💬 Я понимаю только фото одежды. Отправь изображение!")

