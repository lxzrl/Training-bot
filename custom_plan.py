import re
from html import escape

MAX_DAYS = 7
MAX_EXERCISES = 20
DEFAULT_REST = 90

FORMAT_HELP = """Пришли свой план одним сообщением в таком виде:

<code>День 1 — Верх тела
Жим штанги лёжа 4x8-10
Тяга верхнего блока 3x10-12, отдых 60
Планка 3x30-45 сек

День 2 — Ноги
Приседания со штангой 4x6-8, отдых 120
Выпады 3x10 на каждую ногу</code>

• Строка без «подходы x повторы» — название дня
• Упражнение — <b>название подходы x повторы</b>, можно добавить «отдых 90» (в секундах, по умолчанию 90)
• До 7 дней и до 20 упражнений в дне"""

# "Жим лёжа 4x8-10, отдых 90": name, sets, reps, optional rest in seconds.
EXERCISE = re.compile(r"^(?P<name>.+?)[\s:—–-]*(?P<sets>\d{1,2})\s*[xх×*]\s*(?P<reps>.+?)"
                      r"(?:[\s,;]+отдых\s*(?P<rest>\d{1,3})\s*(?:с|сек)?\.?)?$", re.I)
BULLET = re.compile(r"^(?:\d{1,2}[.)]|[•*·-])\s*")


class PlanFormatError(Exception):
    """Message that explains to the user what is wrong with the plan."""


def parse(text: str) -> dict:
    """Turn the user's plain-text plan into the same structure the AI plans use."""
    days: list[dict] = []
    for raw in text.splitlines():
        line = BULLET.sub("", raw.strip()).strip()
        if not line:
            continue
        match = EXERCISE.match(line)
        if match is None:
            days.append(_day(line.rstrip(":").strip()[:60]))
            continue
        if not days:
            days.append(_day("День 1"))
        sets = int(match["sets"])
        if not 1 <= sets <= 20:
            raise PlanFormatError(f"Странное число подходов в строке «{escape(line)}» — укажи от 1 до 20")
        days[-1]["exercises"].append({
            "name": match["name"].strip(" ,.:—–-")[:60],
            "sets": sets,
            "reps": match["reps"].strip(" ,.")[:30],
            "rest_sec": int(match["rest"]) if match["rest"] else DEFAULT_REST,
            "weight_tip": "",
            "note": "",
        })

    days = [d for d in days if d["exercises"]]
    if not days:
        raise PlanFormatError("Не нашёл ни одного упражнения. Упражнение пиши так: <code>Жим лёжа 4x8-10</code>")
    if len(days) > MAX_DAYS:
        raise PlanFormatError(f"Слишком много дней ({len(days)}), максимум {MAX_DAYS}")
    for day in days:
        if len(day["exercises"]) > MAX_EXERCISES:
            raise PlanFormatError(f"В «{escape(day['title'])}» слишком много упражнений, максимум {MAX_EXERCISES}")
    return {
        "summary": "Твой собственный план. Дневник, подсказки по весам и напоминания работают с ним так же, "
                   "как с планом от нейросети.",
        "days": days,
        "progression": "",
        "nutrition_tips": [],
        "safety_note": "",
        "custom": True,
    }


def _day(title: str) -> dict:
    return {"title": title, "warmup": "", "exercises": [], "cooldown": ""}
