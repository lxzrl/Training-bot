import asyncio
import logging
from datetime import date
from html import escape

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError

import db
from handlers.diary import next_day
from keyboards import one_button
from utils import now

log = logging.getLogger(__name__)

BODY_REMINDER_TIME = "12:00"
BODY_REMINDER_DAYS = 30


def _days_since(iso: str | None) -> int:
    return 10**6 if iso is None else (now().date() - date.fromisoformat(iso)).days


async def _workout_reminder(bot: Bot, user: dict, today: str):
    plan = db.get_plan(user["id"])
    text = "⏰ Сегодня день тренировки! 💪"
    if plan:
        text += f"\nПо плану: <b>{escape(plan['days'][next_day(user['id'], plan)]['title'])}</b>"
    text += "\n\nПосле тренировки запиши результаты 👇"
    db.update_user(user["id"], last_remind=today)
    await bot.send_message(user["id"], text, reply_markup=one_button("✍️ Записать тренировку", "w:start"))


async def _body_reminder(bot: Bot, user: dict, today: str):
    history = db.body_history(user["id"], 1)
    last_entry = history[-1]["date"] if history else user["created"]
    if _days_since(last_entry) < BODY_REMINDER_DAYS or _days_since(user["last_body_remind"]) < BODY_REMINDER_DAYS:
        return
    db.update_user(user["id"], last_body_remind=today)
    await bot.send_message(user["id"], "📏 Прошёл месяц — пора обновить замеры! Посмотрим, как ты изменился(ась) 😉",
                           reply_markup=one_button("➕ Записать замер", "body:add"))


async def tick(bot: Bot):
    moment = now()
    hm = moment.strftime("%H:%M")
    today = moment.date().isoformat()
    for user in db.all_users():
        if user["sex"] is None:  # never finished the questionnaire
            continue
        try:
            if (user["remind_on"] and moment.weekday() in user["remind_days"]
                    and user["remind_time"] == hm and user["last_remind"] != today):
                await _workout_reminder(bot, user, today)
            if hm == BODY_REMINDER_TIME:
                await _body_reminder(bot, user, today)
        except TelegramForbiddenError:
            log.info("User %s blocked the bot", user["id"])
        except Exception:
            log.exception("Reminder for user %s failed", user["id"])


async def reminder_loop(bot: Bot):
    while True:
        try:
            await tick(bot)
        except Exception:
            log.exception("Reminder tick failed")
        await asyncio.sleep(60 - now().second)
