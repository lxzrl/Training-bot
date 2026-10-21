from html import escape

from utils import fmt, plural

SEXES = {"m": "Мужской", "f": "Женский"}
GOALS = {
    "lose": "🔥 Похудеть",
    "gain": "💪 Набрать мышцы",
    "strength": "🏋️ Стать сильнее",
    "endurance": "🏃 Выносливость",
    "maintain": "🙂 Поддерживать форму",
}
LEVELS = {
    "beginner": "Новичок (до 6 мес)",
    "mid": "Средний (0,5–2 года)",
    "pro": "Опытный (2+ года)",
}
PLACES = {"gym": "🏢 Зал", "home": "🏠 Дома", "outdoor": "🌳 Улица"}
EQUIPMENT = {
    "dumbbells": "Гантели",
    "barbell": "Штанга",
    "pullup": "Турник",
    "dips": "Брусья",
    "bands": "Резинки",
    "kettlebell": "Гиря",
    "bench": "Скамья",
    "mat": "Коврик",
}
DAYS = {str(n): str(n) for n in range(2, 7)}
DURATIONS = {"30": "30 мин", "45": "45 мин", "60": "60 мин", "90": "90 мин"}

# Asking gym-goers about equipment is pointless: every gym has roughly this.
GYM_EQUIPMENT = (
    "штанги и стойки для приседаний, скамьи (горизонтальная и регулируемая), гантели, гири, "
    "турник и брусья, кроссовер и блочные тренажёры (верхняя и нижняя тяга), тренажёр Смита, "
    "жим ногами, разгибание и сгибание ног, тренажёр для икр, хаммер, баттерфляй, гиперэкстензия, "
    "кардиотренажёры (дорожка, велотренажёр, эллипс, гребной)"
)

DISCLAIMER = ("<i>ℹ️ Я не врач. Если есть болячки или что-то болит на тренировке — "
              "лучше посоветоваться со специалистом.</i>")


def plain(label: str) -> str:
    """Drop the leading emoji from a button label."""
    return label.split(" ", 1)[1] if not label[0].isalnum() else label


def equipment_text(u: dict) -> str:
    if u["place"] == "gym":
        return "стандартный зал"
    items = [EQUIPMENT[k] for k in u["equipment"] if k in EQUIPMENT]
    return ", ".join(items) if items else "только собственный вес"


def bmi(u: dict) -> float:
    return u["weight"] / (u["height"] / 100) ** 2


def bmi_label(value: float) -> str:
    if value < 18.5:
        return "ниже нормы"
    if value < 25:
        return "норма"
    if value < 30:
        return "избыточный вес"
    return "ожирение"


def nutrition(u: dict) -> dict:
    """Daily calories and macros: Mifflin-St Jeor BMR x activity, adjusted for the goal."""
    bmr = 10 * u["weight"] + 6.25 * u["height"] - 5 * u["age"] + (5 if u["sex"] == "m" else -161)
    activity = {2: 1.375, 3: 1.45, 4: 1.55, 5: 1.6, 6: 1.725}.get(u["days"], 1.45)
    adjust = {"lose": 0.85, "gain": 1.1, "strength": 1.05}.get(u["goal"], 1.0)
    calories = bmr * activity * adjust
    protein = u["weight"] * {"lose": 2.0, "gain": 1.8, "strength": 1.8}.get(u["goal"], 1.6)
    fat = u["weight"] * 0.9
    carbs = max(0.0, (calories - protein * 4 - fat * 9) / 4)
    return {"calories": round(calories, -1), "protein": round(protein), "fat": round(fat), "carbs": round(carbs)}


def card(u: dict) -> str:
    n = nutrition(u)
    b = bmi(u)
    sex = "М" if u["sex"] == "m" else "Ж"
    lines = [
        "<b>👤 Твоя анкета</b>",
        f"{sex} · {plural(u['age'], 'год', 'года', 'лет')} · {u['height']} см · {fmt(u['weight'])} кг",
        f"ИМТ: {b:.1f} ({bmi_label(b)})",
        f"Цель: {plain(GOALS[u['goal']])}",
        f"Уровень: {LEVELS[u['level']]}",
        f"Где: {plain(PLACES[u['place']])}",
    ]
    if u["place"] != "gym":
        lines.append(f"Инвентарь: {equipment_text(u)}")
    lines += [
        f"Тренировки: {plural(u['days'], 'раз', 'раза', 'раз')} в неделю по {u['duration']} мин",
        f"Ограничения: {escape(u['injuries']) or 'нет'}",
        "",
        "<b>🍽 КБЖУ на день</b>",
        f"🔥 {n['calories']:.0f} ккал · Б {n['protein']} · Ж {n['fat']} · У {n['carbs']}",
    ]
    return "\n".join(lines)


def describe(u: dict) -> str:
    """Profile summary for the AI prompt."""
    n = nutrition(u)
    sex = "мужчина" if u["sex"] == "m" else "женщина"
    equipment = f"стандартный тренажёрный зал: {GYM_EQUIPMENT}" if u["place"] == "gym" else equipment_text(u)
    return "\n".join([
        "Анкета клиента:",
        f"- {sex}, {plural(u['age'], 'год', 'года', 'лет')}, рост {u['height']} см, вес {fmt(u['weight'])} кг, ИМТ {bmi(u):.1f}",
        f"- Цель: {plain(GOALS[u['goal']])}",
        f"- Уровень подготовки: {LEVELS[u['level']]}",
        f"- Где тренируется: {plain(PLACES[u['place']])}",
        f"- Инвентарь: {equipment}",
        f"- Тренировок в неделю: {u['days']}, длительность одной: {u['duration']} мин",
        f"- Травмы и ограничения: {u['injuries'] or 'нет'}",
        f"- Рассчитанная норма питания: {n['calories']:.0f} ккал, белки {n['protein']} г, "
        f"жиры {n['fat']} г, углеводы {n['carbs']} г",
    ])
