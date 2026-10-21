from html import escape
from urllib.parse import quote_plus

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import LinkPreviewOptions, Message
from aiogram.utils.chat_action import ChatActionSender

import ai
import config
import db
from handlers.base import LIMIT_MESSAGE, NOT_MENU, need_user
from keyboards import BTN_TECH
from utils import split_text

router = Router()


class Tech(StatesGroup):
    name = State()


@router.message(F.text == BTN_TECH)
async def ask_name(message: Message, state: FSMContext):
    await state.clear()
    if not await need_user(message, message.from_user.id):
        return
    await state.set_state(Tech.name)
    await message.answer("Какое упражнение разобрать? Напиши название, например: <i>становая тяга</i>")


@router.message(Tech.name, NOT_MENU)
async def got_name(message: Message, state: FSMContext):
    await state.clear()
    await send_technique(message, message.from_user.id, message.text)


async def send_technique(message: Message, uid: int, name: str):
    name = name.strip()[:100]
    key = name.lower()
    text = db.get_technique(key)
    if text is None:
        if not db.take_ai_credit(uid, config.AI_DAILY_LIMIT):
            await message.answer(LIMIT_MESSAGE)
            return
        try:
            async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
                text = await ai.explain_technique(name)
        except ai.AIError as e:
            await message.answer(f"😔 {e}")
            return
        db.save_technique(key, text)

    url = "https://www.youtube.com/results?search_query=" + quote_plus(f"техника {name}")
    chunks = split_text(text)
    chunks[0] = f"<b>📖 {escape(name)}</b>\n\n" + escape(chunks[0])
    chunks[1:] = [escape(c) for c in chunks[1:]]
    chunks[-1] += f'\n\n🎥 <a href="{url}">Видео с техникой на YouTube</a>'
    for chunk in chunks:
        await message.answer(chunk, link_preview_options=LinkPreviewOptions(is_disabled=True))
