from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

import athlete
import db
from handlers import onboarding
from handlers.base import need_user
from keyboards import BTN_PROFILE, main_menu, one_button

router = Router()
# Included last: catches whatever no other handler took.
fallback_router = Router()

HELP = f"""<b>Что я умею</b>

📋 <b>Мой план</b> — программа тренировок и КБЖУ под твою цель
✍️ <b>Записать тренировку</b> — дневник: веса, повторы и подсказки, когда добавлять нагрузку
📈 <b>Прогресс</b> — как растут результаты и вес
⚖️ <b>Замеры</b> — вес и талия (раз в месяц напомню)
🔍 <b>Разбор плана</b> — пришли свою программу, а я скажу, что в ней поменять
📖 <b>Техника</b> — как правильно делать упражнение
⏰ <b>Напоминания</b> — напомню о тренировке в нужные дни
👤 <b>Анкета</b> — твои данные, можно заполнить заново

/cancel — отменить текущее действие

{athlete.DISCLAIMER}"""


@router.message(CommandStart())
async def start(message: Message, state: FSMContext):
    await state.clear()
    user = db.get_user(message.from_user.id)
    if user:
        await message.answer(f"С возвращением, {escape(user['name'])}! 💪", reply_markup=main_menu())
        return
    await message.answer("Привет! Я твой персональный тренер 🏋️\n\n"
                         "Задам несколько вопросов — и составлю программу тренировок и КБЖУ под твою цель. "
                         "Это займёт пару минут.", reply_markup=ReplyKeyboardRemove())
    await onboarding.begin(message, state)


@router.message(Command("help"))
async def help_(message: Message):
    await message.answer(HELP)


@router.message(Command("cancel"))
@router.message(Command("menu"))
async def cancel(message: Message, state: FSMContext):
    await state.clear()
    if db.get_user(message.from_user.id):
        await message.answer("Ок, главное меню 👇", reply_markup=main_menu())
    else:
        await message.answer("Нажми /start, чтобы начать 🙂")


@router.message(F.text == BTN_PROFILE)
async def profile(message: Message, state: FSMContext):
    await state.clear()
    user = await need_user(message, message.from_user.id)
    if user:
        await message.answer(athlete.card(user), reply_markup=one_button("✏️ Заполнить заново", "profile:edit"))


@router.callback_query(F.data == "profile:edit")
async def profile_edit(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await onboarding.begin(cb.message, state)


@fallback_router.message()
async def unknown(message: Message):
    if db.get_user(message.from_user.id):
        await message.answer("Не понял 🙂 Выбери что-нибудь в меню 👇", reply_markup=main_menu())
    else:
        await message.answer("Нажми /start, чтобы начать 🙂")


@fallback_router.callback_query()
async def stale_button(cb: CallbackQuery):
    await cb.answer("Эта кнопка уже не активна", show_alert=False)
