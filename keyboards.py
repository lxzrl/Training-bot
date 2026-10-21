from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

BTN_PLAN = "📋 Мой план"
BTN_LOG = "✍️ Записать тренировку"
BTN_PROGRESS = "📈 Прогресс"
BTN_BODY = "⚖️ Замеры"
BTN_ANALYZE = "🔍 Разбор плана"
BTN_TECH = "📖 Техника"
BTN_REMIND = "⏰ Напоминания"
BTN_PROFILE = "👤 Анкета"

MENU_BUTTONS = {BTN_PLAN, BTN_LOG, BTN_PROGRESS, BTN_BODY, BTN_ANALYZE, BTN_TECH, BTN_REMIND, BTN_PROFILE}


def main_menu() -> ReplyKeyboardMarkup:
    rows = [
        [BTN_PLAN, BTN_LOG],
        [BTN_PROGRESS, BTN_BODY],
        [BTN_ANALYZE, BTN_TECH],
        [BTN_REMIND, BTN_PROFILE],
    ]
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=t) for t in row] for row in rows],
                               resize_keyboard=True)


def choices(prefix: str, options: dict[str, str], per_row: int = 2) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, label in options.items():
        builder.button(text=label, callback_data=f"{prefix}:{key}")
    builder.adjust(per_row)
    return builder.as_markup()


def one_button(text: str, data: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, callback_data=data)]])
