from aiogram import BaseMiddleware
from aiogram.types import Message

import config


class AccessMiddleware(BaseMiddleware):
    """Lets only the owner and users from ALLOWED_USERS through (when the list is set)."""

    async def __call__(self, handler, event, data):
        user = data.get("event_from_user")
        allowed = config.ALLOWED_USERS | {config.ADMIN_ID}
        if config.ALLOWED_USERS and (user is None or user.id not in allowed):
            if isinstance(event, Message) and user:
                await event.answer("Это закрытый бот 🙂 Попроси владельца добавить тебя.\n"
                                   f"Твой ID: <code>{user.id}</code>")
            return None
        return await handler(event, data)
