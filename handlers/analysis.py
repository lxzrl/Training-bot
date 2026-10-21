from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from aiogram.utils.chat_action import ChatActionSender

import ai
import athlete
import config
import db
from handlers.base import LIMIT_MESSAGE, NOT_MENU, need_user
from keyboards import BTN_ANALYZE
from utils import split_text

router = Router()


class Analyze(StatesGroup):
    plan = State()


@router.message(F.text == BTN_ANALYZE)
async def ask_plan(message: Message, state: FSMContext):
    await state.clear()
    if not await need_user(message, message.from_user.id):
        return
    await state.set_state(Analyze.plan)
    await message.answer("Пришли свою программу тренировок одним сообщением: дни, упражнения, подходы и повторы. "
                         "Разберу, что в ней хорошо и что стоит поменять под твою цель 🔍")


@router.message(Analyze.plan, NOT_MENU)
async def got_plan(message: Message, state: FSMContext):
    if len(message.text) < 30:
        await message.answer("Маловато 🙂 Пришли план целиком: дни, упражнения, подходы и повторы")
        return
    await state.clear()
    uid = message.from_user.id
    user = db.get_user(uid)
    if not db.take_ai_credit(uid, config.AI_DAILY_LIMIT):
        await message.answer(LIMIT_MESSAGE)
        return
    try:
        async with ChatActionSender.typing(bot=message.bot, chat_id=message.chat.id):
            review = await ai.analyze_plan(athlete.describe(user), message.text[:6000])
    except ai.AIError as e:
        await message.answer(f"😔 {e}")
        return
    for chunk in split_text(review):
        await message.answer(escape(chunk))


@router.message(Analyze.plan, ~F.text)
async def not_text(message: Message):
    await message.answer("Пришли план, пожалуйста, текстом — картинки и файлы я пока не читаю 🙏")
