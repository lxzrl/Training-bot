from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import db
from handlers.base import NOT_MENU, need_user, parse_number
from keyboards import BTN_BODY, one_button
from utils import fmt, short_date, sparkline

router = Router()


class Body(StatesGroup):
    weight = State()
    waist = State()


def history_text(uid: int) -> str:
    history = db.body_history(uid, 8)
    if not history:
        return "<b>⚖️ Замеры</b>\n\nПока записей нет. Добавь первый замер — и будем следить за прогрессом 📏"
    lines = ["<b>⚖️ Замеры</b>", ""]
    previous = None
    for entry in history:
        line = f"{short_date(entry['date'])} — {fmt(entry['weight'])} кг"
        if previous is not None and entry["weight"] != previous:
            line += f" ({'+' if entry['weight'] > previous else '−'}{fmt(abs(entry['weight'] - previous))})"
        if entry["waist"]:
            line += f" · талия {fmt(entry['waist'])} см"
        lines.append(line)
        previous = entry["weight"]
    if chart := sparkline([e["weight"] for e in history]):
        lines += ["", f"Вес: {chart}"]
    return "\n".join(lines)


@router.message(F.text == BTN_BODY)
async def body_menu(message: Message, state: FSMContext):
    await state.clear()
    if not await need_user(message, message.from_user.id):
        return
    await message.answer(history_text(message.from_user.id), reply_markup=one_button("➕ Новый замер", "body:add"))


@router.callback_query(F.data == "body:add")
async def add(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    if not await need_user(cb.message, cb.from_user.id):
        return
    await state.set_state(Body.weight)
    await cb.message.answer("Сколько весишь сейчас? (кг)")


@router.message(Body.weight, NOT_MENU)
async def got_weight(message: Message, state: FSMContext):
    weight = parse_number(message.text)
    if weight is None or not 30 <= weight <= 250:
        await message.answer("Напиши вес в килограммах, например 72.4")
        return
    await state.update_data(weight=round(weight, 1))
    await state.set_state(Body.waist)
    await message.answer("А обхват талии? (см, на уровне пупка)",
                         reply_markup=one_button("Пропустить ⏭", "body:skip"))


@router.message(Body.waist, NOT_MENU)
async def got_waist(message: Message, state: FSMContext):
    waist = parse_number(message.text)
    if waist is None or not 40 <= waist <= 200:
        await message.answer("Напиши обхват в сантиметрах, например 80")
        return
    await save(message, state, message.from_user.id, round(waist, 1))


@router.callback_query(Body.waist, F.data == "body:skip")
async def skip_waist(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=None)
    await save(cb.message, state, cb.from_user.id, None)


async def save(message: Message, state: FSMContext, uid: int, waist: float | None):
    weight = (await state.get_data())["weight"]
    await state.clear()
    old_weight = db.get_user(uid)["weight"]
    db.add_body(uid, weight, waist)
    db.update_user(uid, weight=weight)

    text = f"✅ Записано! КБЖУ пересчитано под новый вес.\n\n{history_text(uid)}"
    markup = None
    if abs(weight - old_weight) >= 3 and db.get_plan(uid):
        text += "\n\nВес заметно изменился — можно обновить и план тренировок 👇"
        builder = InlineKeyboardBuilder()
        builder.button(text="🔄 Новый план", callback_data="plan:new")
        markup = builder.as_markup()
    await message.answer(text, reply_markup=markup)
