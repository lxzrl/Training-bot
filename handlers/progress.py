from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

import db
from handlers.base import need_user
from keyboards import BTN_PROGRESS
from utils import fmt, sparkline, today

router = Router()


def exercise_line(name: str, entries: list[dict]) -> str:
    first, last = entries[0], entries[-1]
    if any(e["weight"] for e in entries):
        values = [e["weight"] for e in entries]
        change = f"{fmt(first['weight'])} → {fmt(last['weight'])} кг"
    else:
        values = [max(e["reps"]) for e in entries]
        change = f"{values[0]} → {values[-1]} повт."
    return f"• {escape(name)}: {change} {sparkline(values[-8:])}"


@router.message(F.text == BTN_PROGRESS)
async def progress(message: Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    if not await need_user(message, uid):
        return
    dates = db.workout_dates(uid)
    history = db.exercise_history(uid)
    body = db.body_history(uid, 12)
    if not dates and not body:
        await message.answer("Пока пусто 🙂 Запиши первую тренировку через «✍️ Записать тренировку» — "
                             "и тут появится твой прогресс.")
        return

    month = today()[:7]
    lines = [
        "<b>📈 Прогресс</b>",
        "",
        f"Тренировок: всего {len(dates)}, в этом месяце {sum(d.startswith(month) for d in dates)}",
    ]
    if history:
        lines += ["", "<b>Упражнения</b> (первая → последняя запись):"]
        top = sorted(history.items(), key=lambda kv: -len(kv[1]))[:10]
        lines += [exercise_line(name, entries) for name, entries in top]
    if body:
        weights = [e["weight"] for e in body]
        lines += ["", f"<b>Вес:</b> {fmt(weights[0])} → {fmt(weights[-1])} кг {sparkline(weights)}"]
    await message.answer("\n".join(lines))
