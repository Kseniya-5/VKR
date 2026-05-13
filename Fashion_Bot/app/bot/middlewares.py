from aiogram import BaseMiddleware
from aiogram.types import Message

class LoggingMiddleware(BaseMiddleware):
    def __init__(self):
        super().__init__()

    async def __call__(self, handler, event: Message, data: dict):
        print(f'Получено сообщение: {event.text}')
        return await handler(event, data)