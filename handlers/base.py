from aiogram import F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

import db
from keyboards import MENU_BUTTONS

# Text input that isn't a main-menu button, so menu presses always escape an input step.
NOT_MENU = F.text & ~F.text.in_(MENU_BUTTONS)

LIMIT_MESSAGE = "На сегодня лимит запросов к нейросети исчерпан, приходи завтра 🙂"


async def need_user(message: Message, uid: int) -> dict | None:
    user = db.get_user(uid)
    if user is None:
        await message.answer("Сначала давай познакомимся — нажми /start 🙂")
    return user


async def safe_edit(message: Message, text: str, reply_markup=None):
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "not modified" not in str(e):
            raise


def parse_number(text: str | None) -> float | None:
    if not text:
        return None
    try:
        return float(text.strip().replace(",", ".").split()[0])
    except (ValueError, IndexError):
        return None
