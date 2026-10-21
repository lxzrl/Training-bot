from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import athlete
import db
from handlers.base import NOT_MENU, parse_number
from keyboards import choices, main_menu, one_button

router = Router()


class Form(StatesGroup):
    sex = State()
    age = State()
    height = State()
    weight = State()
    goal = State()
    level = State()
    place = State()
    equipment = State()
    days = State()
    duration = State()
    injuries = State()


def equipment_kb(selected: list[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, label in athlete.EQUIPMENT.items():
        builder.button(text=("✅ " if key in selected else "") + label, callback_data=f"eq:{key}")
    builder.button(text="Готово ➡️", callback_data="eq:done")
    builder.adjust(2)
    return builder.as_markup()


async def begin(message: Message, state: FSMContext):
    await state.clear()
    await state.set_state(Form.sex)
    await message.answer("<b>1/10.</b> Твой пол?", reply_markup=choices("sex", athlete.SEXES))


async def _picked(cb: CallbackQuery, state: FSMContext, field: str, options: dict[str, str]) -> str:
    """Store the chosen option and replace the question's buttons with the answer."""
    key = cb.data.split(":", 1)[1]
    await state.update_data(**{field: key})
    await cb.answer()
    await cb.message.edit_text(f"{cb.message.html_text}\n👉 {options[key]}")
    return key


async def _number(message: Message, lo: float, hi: float, error: str) -> float | None:
    value = parse_number(message.text)
    if value is None or not lo <= value <= hi:
        await message.answer(error)
        return None
    return value


@router.callback_query(Form.sex, F.data.startswith("sex:"))
async def got_sex(cb: CallbackQuery, state: FSMContext):
    await _picked(cb, state, "sex", athlete.SEXES)
    await state.set_state(Form.age)
    await cb.message.answer("<b>2/10.</b> Сколько тебе лет?")


@router.message(Form.age, NOT_MENU)
async def got_age(message: Message, state: FSMContext):
    if (age := await _number(message, 12, 90, "Напиши возраст числом, например 25")) is None:
        return
    await state.update_data(age=int(age))
    await state.set_state(Form.height)
    await message.answer("<b>3/10.</b> Рост в сантиметрах?")


@router.message(Form.height, NOT_MENU)
async def got_height(message: Message, state: FSMContext):
    if (height := await _number(message, 120, 230, "Напиши рост в сантиметрах, например 175")) is None:
        return
    await state.update_data(height=int(height))
    await state.set_state(Form.weight)
    await message.answer("<b>4/10.</b> Вес в килограммах?")


@router.message(Form.weight, NOT_MENU)
async def got_weight(message: Message, state: FSMContext):
    if (weight := await _number(message, 30, 250, "Напиши вес в килограммах, например 70.5")) is None:
        return
    await state.update_data(weight=round(weight, 1))
    await state.set_state(Form.goal)
    await message.answer("<b>5/10.</b> Какая цель?", reply_markup=choices("goal", athlete.GOALS, 1))


@router.callback_query(Form.goal, F.data.startswith("goal:"))
async def got_goal(cb: CallbackQuery, state: FSMContext):
    await _picked(cb, state, "goal", athlete.GOALS)
    await state.set_state(Form.level)
    await cb.message.answer("<b>6/10.</b> Какой у тебя опыт тренировок?",
                            reply_markup=choices("level", athlete.LEVELS, 1))


@router.callback_query(Form.level, F.data.startswith("level:"))
async def got_level(cb: CallbackQuery, state: FSMContext):
    await _picked(cb, state, "level", athlete.LEVELS)
    await state.set_state(Form.place)
    await cb.message.answer("<b>7/10.</b> Где будешь тренироваться?",
                            reply_markup=choices("place", athlete.PLACES, 3))


@router.callback_query(Form.place, F.data.startswith("place:"))
async def got_place(cb: CallbackQuery, state: FSMContext):
    place = await _picked(cb, state, "place", athlete.PLACES)
    await state.update_data(equipment=[])
    if place == "gym":
        await ask_days(cb.message, state)
        return
    await state.set_state(Form.equipment)
    await cb.message.answer("<b>7½.</b> Что есть из инвентаря? Отметь всё нужное.\n"
                            "Если ничего нет — просто жми «Готово».", reply_markup=equipment_kb([]))


@router.callback_query(Form.equipment, F.data.startswith("eq:"))
async def got_equipment(cb: CallbackQuery, state: FSMContext):
    key = cb.data.split(":", 1)[1]
    selected = (await state.get_data())["equipment"]
    if key == "done":
        await cb.answer()
        chosen = ", ".join(athlete.EQUIPMENT[k] for k in selected) or "только собственный вес"
        await cb.message.edit_text(f"{cb.message.html_text}\n👉 {chosen}")
        await ask_days(cb.message, state)
        return
    selected = [k for k in selected if k != key] if key in selected else selected + [key]
    await state.update_data(equipment=selected)
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=equipment_kb(selected))


async def ask_days(message: Message, state: FSMContext):
    await state.set_state(Form.days)
    await message.answer("<b>8/10.</b> Сколько раз в неделю готов(а) тренироваться?",
                         reply_markup=choices("days", athlete.DAYS, 5))


@router.callback_query(Form.days, F.data.startswith("days:"))
async def got_days(cb: CallbackQuery, state: FSMContext):
    await _picked(cb, state, "days", athlete.DAYS)
    await state.set_state(Form.duration)
    await cb.message.answer("<b>9/10.</b> Сколько времени на одну тренировку?",
                            reply_markup=choices("dur", athlete.DURATIONS, 4))


@router.callback_query(Form.duration, F.data.startswith("dur:"))
async def got_duration(cb: CallbackQuery, state: FSMContext):
    await _picked(cb, state, "duration", athlete.DURATIONS)
    await state.set_state(Form.injuries)
    await cb.message.answer("<b>10/10.</b> Есть травмы или ограничения по здоровью? Напиши коротко, "
                            "например «болит колено» или «грыжа в пояснице».",
                            reply_markup=one_button("Нет, всё в порядке 👍", "inj:none"))


@router.message(Form.injuries, NOT_MENU)
async def got_injuries(message: Message, state: FSMContext):
    await finish(message, state, message.from_user.id, message.from_user.first_name, message.text.strip()[:300])


@router.callback_query(Form.injuries, F.data == "inj:none")
async def no_injuries(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=None)
    await finish(cb.message, state, cb.from_user.id, cb.from_user.first_name, "")


async def finish(message: Message, state: FSMContext, uid: int, name: str, injuries: str):
    data = await state.get_data()
    await state.clear()
    db.save_profile(uid, {
        "name": name or "друг",
        "sex": data["sex"],
        "age": data["age"],
        "height": data["height"],
        "weight": data["weight"],
        "goal": data["goal"],
        "level": data["level"],
        "place": data["place"],
        "equipment": data["equipment"],
        "days": int(data["days"]),
        "duration": int(data["duration"]),
        "injuries": injuries,
    })
    user = db.get_user(uid)
    await message.answer("Готово, анкета сохранена ✅", reply_markup=main_menu())
    await message.answer(f"{athlete.card(user)}\n\n{athlete.DISCLAIMER}",
                         reply_markup=one_button("🏋️ Составить план", "plan:new"))
