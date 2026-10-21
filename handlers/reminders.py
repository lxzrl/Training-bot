import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import db
from handlers.base import NOT_MENU, need_user, safe_edit
from keyboards import BTN_REMIND

router = Router()

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
TIMES = ["07:00", "08:00", "09:00", "12:00", "17:00", "18:00", "19:00", "20:00"]


class Remind(StatesGroup):
    time = State()


def settings_text(user: dict) -> str:
    days = ", ".join(WEEKDAYS[d] for d in sorted(user["remind_days"])) or "не выбраны"
    status = "🔔 включены" if user["remind_on"] else "🔕 выключены"
    return (f"<b>⏰ Напоминания</b> — {status}\n\n"
            f"Дни: {days}\nВремя: {user['remind_time']}\n\n"
            "Отметь дни тренировок и время. А раз в месяц я сам напомню обновить замеры 📏")


def settings_kb(user: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i, name in enumerate(WEEKDAYS):
        builder.button(text=("✅" if i in user["remind_days"] else "") + name, callback_data=f"rd:{i}")
    for t in TIMES:
        builder.button(text=("• " if t == user["remind_time"] else "") + t, callback_data=f"rt:{t}")
    builder.button(text="✏️ Другое время", callback_data="rt:custom")
    builder.button(text="🔕 Выключить" if user["remind_on"] else "🔔 Включить", callback_data="ron")
    builder.adjust(7, 4, 4, 2)
    return builder.as_markup()


@router.message(F.text == BTN_REMIND)
async def show(message: Message, state: FSMContext):
    await state.clear()
    user = await need_user(message, message.from_user.id)
    if user:
        await message.answer(settings_text(user), reply_markup=settings_kb(user))


async def _refresh(cb: CallbackQuery):
    user = db.get_user(cb.from_user.id)
    await safe_edit(cb.message, settings_text(user), settings_kb(user))


@router.callback_query(F.data.startswith("rd:"))
async def toggle_day(cb: CallbackQuery):
    user = db.get_user(cb.from_user.id)
    day = int(cb.data[3:])
    days = sorted(set(user["remind_days"]) ^ {day})
    # Picking the first day switches reminders on; it's what people expect.
    db.update_user(cb.from_user.id, remind_days=days, remind_on=1 if days else 0)
    await cb.answer()
    await _refresh(cb)


@router.callback_query(F.data.startswith("rt:"))
async def set_time(cb: CallbackQuery, state: FSMContext):
    value = cb.data[3:]
    await cb.answer()
    if value == "custom":
        await state.set_state(Remind.time)
        await cb.message.answer("Напиши время в формате ЧЧ:ММ, например 06:30")
        return
    db.update_user(cb.from_user.id, remind_time=value)
    await _refresh(cb)


@router.message(Remind.time, NOT_MENU)
async def got_time(message: Message, state: FSMContext):
    match = re.fullmatch(r"\s*(\d{1,2})[:.](\d{2})\s*", message.text)
    if not match or int(match[1]) > 23 or int(match[2]) > 59:
        await message.answer("Не понял 🤔 Напиши время так: 06:30")
        return
    await state.clear()
    uid = message.from_user.id
    db.update_user(uid, remind_time=f"{int(match[1]):02d}:{match[2]}")
    user = db.get_user(uid)
    await message.answer(settings_text(user), reply_markup=settings_kb(user))


@router.callback_query(F.data == "ron")
async def toggle(cb: CallbackQuery):
    user = db.get_user(cb.from_user.id)
    if not user["remind_on"] and not user["remind_days"]:
        await cb.answer("Сначала выбери дни тренировок", show_alert=True)
        return
    db.update_user(cb.from_user.id, remind_on=0 if user["remind_on"] else 1)
    await cb.answer()
    await _refresh(cb)
