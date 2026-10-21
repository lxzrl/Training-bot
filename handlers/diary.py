from html import escape

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

import db
import progression
from handlers.base import NOT_MENU, need_user
from handlers.technique import send_technique
from keyboards import BTN_LOG
from utils import fmt, short_date

router = Router()


class Diary(StatesGroup):
    entering = State()


def next_day(uid: int, plan: dict) -> int:
    last = db.last_workout(uid)
    return 0 if last is None else (last["day_idx"] + 1) % len(plan["days"])


def exercise_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⏭ Пропустить", callback_data="w:skip")
    builder.button(text="📖 Как делать?", callback_data="w:tech")
    builder.button(text="🏁 Закончить", callback_data="w:end")
    builder.adjust(2, 1)
    return builder.as_markup()


async def choose_day(message: Message, uid: int):
    if not await need_user(message, uid):
        return
    plan = db.get_plan(uid)
    if plan is None:
        await message.answer("Сначала нужен план — нажми «📋 Мой план» 🙂")
        return
    suggested = next_day(uid, plan)
    builder = InlineKeyboardBuilder()
    for i, day in enumerate(plan["days"]):
        builder.button(text=("⭐ " if i == suggested else "") + day["title"][:60], callback_data=f"w:day:{i}")
    builder.adjust(1)
    await message.answer("Какую тренировку делаешь? ⭐ — следующая по плану", reply_markup=builder.as_markup())


@router.message(F.text == BTN_LOG)
async def log_button(message: Message, state: FSMContext):
    await state.clear()
    await choose_day(message, message.from_user.id)


@router.callback_query(F.data == "w:start")
async def log_from_reminder(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    await choose_day(cb.message, cb.from_user.id)


@router.callback_query(F.data.startswith("w:day:"))
async def start_day(cb: CallbackQuery, state: FSMContext):
    i = int(cb.data.rsplit(":", 1)[1])
    plan = db.get_plan(cb.from_user.id)
    if plan is None or i >= len(plan["days"]):
        await cb.answer("План изменился, выбери день заново")
        return
    await cb.answer()
    await state.set_state(Diary.entering)
    await state.update_data(day=i, ex=0, workout=None, done=[], prompt=None)
    await cb.message.edit_text(f"Погнали: <b>{escape(plan['days'][i]['title'])}</b> 💪")
    await ask_exercise(cb.message, state, cb.from_user.id)


async def _drop_buttons(bot: Bot, chat_id: int, message_id: int | None):
    if message_id is None:
        return
    try:
        await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
    except TelegramBadRequest:
        pass


async def _current(state: FSMContext, uid: int) -> tuple[dict, dict, dict] | None:
    """State data, plan day and current exercise; None if the plan changed under us."""
    data = await state.get_data()
    plan = db.get_plan(uid)
    if plan is None or data.get("day") is None or data["day"] >= len(plan["days"]):
        return None
    day = plan["days"][data["day"]]
    exercise = day["exercises"][data["ex"]] if data["ex"] < len(day["exercises"]) else None
    return data, day, exercise


async def ask_exercise(message: Message, state: FSMContext, uid: int):
    current = await _current(state, uid)
    if current is None:
        await state.clear()
        await message.answer("План изменился — начни запись заново 🙂")
        return
    data, day, ex = current
    await _drop_buttons(message.bot, message.chat.id, data["prompt"])
    if ex is None:
        await finish(message, state)
        return

    lines = [
        f"<b>{data['ex'] + 1}/{len(day['exercises'])}. {escape(ex['name'])}</b>",
        f"План: {ex['sets']}×{escape(ex['reps'])}, отдых {ex['rest_sec']} с",
    ]
    last = db.last_result(uid, ex["name"], data["workout"])
    if last:
        lines.append(f"Прошлый раз ({short_date(last['date'])}): "
                     f"{progression.format_result(last['weight'], last['reps'])}")
        if tip := progression.advice(ex["reps"], ex["sets"], last["weight"], last["reps"]):
            lines.append(tip)
    elif ex["weight_tip"]:
        lines.append(f"💡 {escape(ex['weight_tip'])}")
    lines.append("\nНапиши результат: <code>60 x 10 10 9 8</code>\nБез веса — только повторы: <code>12 12 10</code>")
    prompt = await message.answer("\n".join(lines), reply_markup=exercise_kb())
    await state.update_data(prompt=prompt.message_id)


@router.message(Diary.entering, NOT_MENU)
async def got_result(message: Message, state: FSMContext):
    parsed = progression.parse_result(message.text)
    if parsed is None:
        await message.answer("Не понял 🤔 Пример: <code>60 x 10 10 9 8</code> или <code>12 12 10</code>")
        return
    uid = message.from_user.id
    current = await _current(state, uid)
    if current is None or current[2] is None:
        await ask_exercise(message, state, uid)
        return
    data, day, ex = current
    weight, reps = parsed

    workout = data["workout"] or db.create_workout(uid, data["day"], day["title"])
    previous_best = db.best_weight(uid, ex["name"], workout)
    record = bool(weight and previous_best is not None and weight > previous_best)
    db.log_result(workout, uid, ex["name"], weight, reps)

    done = data["done"] + [{"name": ex["name"], "weight": weight, "reps": reps, "record": record}]
    await state.update_data(workout=workout, ex=data["ex"] + 1, done=done)
    await message.answer("✅ Есть!" + (" 🏆 Новый рекорд!" if record else ""))
    await ask_exercise(message, state, uid)


@router.callback_query(Diary.entering, F.data == "w:skip")
async def skip(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    data = await state.get_data()
    await state.update_data(ex=data["ex"] + 1)
    await ask_exercise(cb.message, state, cb.from_user.id)


@router.callback_query(Diary.entering, F.data == "w:tech")
async def technique(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    current = await _current(state, cb.from_user.id)
    if current and current[2]:
        await send_technique(cb.message, cb.from_user.id, current[2]["name"])


@router.callback_query(Diary.entering, F.data == "w:end")
async def end(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await cb.message.edit_reply_markup(reply_markup=None)
    await finish(cb.message, state)


@router.callback_query(F.data.in_({"w:skip", "w:tech", "w:end"}))
async def stale(cb: CallbackQuery):
    await cb.answer("Эта тренировка уже не активна — начни запись заново")


async def finish(message: Message, state: FSMContext):
    done = (await state.get_data()).get("done", [])
    await state.clear()
    if not done:
        await message.answer("Тренировка закрыта без записей. В следующий раз всё получится 💪")
        return
    volume = sum(d["weight"] * sum(d["reps"]) for d in done)
    lines = ["🏁 <b>Тренировка записана!</b>", f"Упражнений: {len(done)}"]
    if volume:
        lines.append(f"Общий тоннаж: {fmt(volume)} кг")
    if records := [escape(d["name"]) for d in done if d["record"]]:
        lines.append("🏆 Рекорды: " + ", ".join(records))
    lines.append("\nОтличная работа! Теперь поесть белка и хорошо выспаться 😴")
    await message.answer("\n".join(lines))
