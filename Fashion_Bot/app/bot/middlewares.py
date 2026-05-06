from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from typing import Callable, Dict, Any, Awaitable, Union


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[Union[Message, CallbackQuery], Dict[str, Any]], Awaitable[Any]],
        event: Union[Message, CallbackQuery],
        data: Dict[str, Any]
    ) -> Any:
        if isinstance(event, Message):
            print(f'[MIDDLEWARE] Получено сообщение: {event.text}')
        elif isinstance(event, CallbackQuery):
            print(f'[MIDDLEWARE] Получен callback: {event.data} от user_id={event.from_user.id}')
        
        return await handler(event, data)