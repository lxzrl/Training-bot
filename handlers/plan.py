from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.chat_action import ChatActionSender
from aiogram.utils.keyboard import InlineKeyboardBuilder

import ai
import athlete
import config
import db
from handlers.base import LIMIT_MESSAGE, need_user, safe_edit
from keyboards import BTN_PLAN, one_button
from utils import short_date

router = Router()
generating: set[int] = set()


def overview(plan: dict) -> str:
    lines = [f"<b>📋 Твой план</b> (от {short_date(plan['created'])})", "", escape(plan["summary"]), "", "<b>Неделя:</b>"]
    for day in plan["days"]:
        lines.append(f"• {escape(day['title'])} — {len(day['exercises'])} упр.")
    lines += ["", f"📈 <b>Как прогрессировать:</b> {escape(plan['progression'])}"]
    if plan["safety_note"]:
        lines += ["", f"⚠️ {escape(plan['safety_note'])}"]
    lines += ["", "Нажми на день, чтобы посмотреть упражнения 👇"]
    return "\n".join(lines)


def overview_kb(plan: dict) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for i, day in enumerate(plan["days"]):
        builder.button(text=day["title"][:60], callback_data=f"plan:day:{i}")
    builder.button(text="🥗 Питание", callback_data="plan:food")
    builder.button(text="🔄 Новый план", callback_data="plan:new")
    builder.adjust(*[1] * len(plan["days"]), 2)
    return builder.as_markup()


def day_text(day: dict) -> str:
    lines = [f"<b>{escape(day['title'])}</b>", "", f"🔥 <b>Разминка:</b> {escape(day['warmup'])}", ""]
    for i, ex in enumerate(day["exercises"], 1):
        lines.append(f"{i}. <b>{escape(ex['name'])}</b> — {ex['sets']}×{escape(ex['reps'])}, отдых {ex['rest_sec']} с")
        if ex["weight_tip"]:
            lines.append(f"   💡 {escape(ex['weight_tip'])}")
        if ex["note"]:
            lines.append(f"   📝 {escape(ex['note'])}")
    lines += ["", f"🧘 <b>Заминка:</b> {escape(day['cooldown'])}"]
    return "\n".join(lines)


def food_text(user: dict, plan: dict) -> str:
    n = athlete.nutrition(user)
    lines = [
        "<b>🥗 Питание</b>",
        "",
        f"🔥 {n['calories']:.0f} ккал в день",
        f"Белки {n['protein']} г · Жиры {n['fat']} г · Углеводы {n['carbs']} г",
        "",
    ]
    lines += [f"• {escape(tip)}" for tip in plan["nutrition_tips"]]
    lines += ["", "<i>Норма посчитана по формуле Миффлина — Сан Жеора с учётом тренировок и цели. "
                  "Она пересчитается, когда обновишь вес в «Замерах».</i>"]
    return "\n".join(lines)


back_kb = one_button("⬅️ К плану", "plan:show")


@router.message(F.text == BTN_PLAN)
async def show_plan(message: Message, state: FSMContext):
    await state.clear()
    if not await need_user(message, message.from_user.id):
        return
    plan = db.get_plan(message.from_user.id)
    if plan is None:
        await message.answer("У тебя пока нет плана. Составим? 🏋️", reply_markup=one_button("🏋️ Составить план", "plan:new"))
        return
    await message.answer(overview(plan), reply_markup=overview_kb(plan))


@router.callback_query(F.data == "plan:show")
async def back_to_plan(cb: CallbackQuery):
    await cb.answer()
    if plan := db.get_plan(cb.from_user.id):
        await safe_edit(cb.message, overview(plan), overview_kb(plan))


@router.callback_query(F.data.startswith("plan:day:"))
async def show_day(cb: CallbackQuery):
    await cb.answer()
    plan = db.get_plan(cb.from_user.id)
    i = int(cb.data.rsplit(":", 1)[1])
    if plan and i < len(plan["days"]):
        await safe_edit(cb.message, day_text(plan["days"][i]), back_kb)


@router.callback_query(F.data == "plan:food")
async def show_food(cb: CallbackQuery):
    await cb.answer()
    plan = db.get_plan(cb.from_user.id)
    user = db.get_user(cb.from_user.id)
    if plan and user:
        await safe_edit(cb.message, food_text(user, plan), back_kb)


@router.callback_query(F.data == "plan:new")
async def new_plan(cb: CallbackQuery):
    if db.get_plan(cb.from_user.id) is None:
        await generate(cb)
        return
    await cb.answer()
    builder = InlineKeyboardBuilder()
    builder.button(text="Да, новый план", callback_data="plan:generate")
    builder.button(text="Отмена", callback_data="plan:show")
    await cb.message.answer("Текущий план заменится новым, а дневник тренировок сохранится. Составляем?",
                            reply_markup=builder.as_markup())


@router.callback_query(F.data == "plan:generate")
async def confirm_new_plan(cb: CallbackQuery):
    await cb.message.edit_reply_markup(reply_markup=None)
    await generate(cb)


async def generate(cb: CallbackQuery):
    uid = cb.from_user.id
    user = db.get_user(uid)
    if user is None:
        await cb.answer("Сначала заполни анкету: /start", show_alert=True)
        return
    if uid in generating:
        await cb.answer("Уже составляю, подожди чуть-чуть ⏳")
        return
    if not db.take_ai_credit(uid, config.AI_DAILY_LIMIT):
        await cb.answer(LIMIT_MESSAGE, show_alert=True)
        return
    await cb.answer()
    generating.add(uid)
    wait = await cb.message.answer("Составляю план под тебя… Обычно это занимает до пары минут ⏳")
    try:
        async with ChatActionSender.typing(bot=cb.bot, chat_id=cb.message.chat.id):
            plan = await ai.generate_plan(athlete.describe(user))
    except ai.AIError as e:
        await wait.edit_text(f"😔 {e}")
        return
    finally:
        generating.discard(uid)
    db.save_plan(uid, plan.model_dump())
    saved = db.get_plan(uid)
    await wait.delete()
    await cb.message.answer(overview(saved), reply_markup=overview_kb(saved))
