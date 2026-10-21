import re

from utils import fmt


def parse_result(text: str) -> tuple[float, list[int]] | None:
    """'60 x 10 10 9' -> (60.0, [10, 10, 9]); '12 12 10' -> (0.0, [12, 12, 10])."""
    t = text.lower()
    for sign in ("х", "×", "*"):
        t = t.replace(sign, "x")
    if "x" in t:
        weight_part, _, reps_part = t.partition("x")
        found = re.findall(r"\d+(?:[.,]\d+)?", weight_part)
        if len(found) != 1:
            return None
        weight = float(found[0].replace(",", "."))
    else:
        weight, reps_part = 0.0, t
    reps = [int(r) for r in re.findall(r"\d+", reps_part)]
    if not 1 <= len(reps) <= 12 or not all(0 < r <= 1000 for r in reps) or not 0 <= weight <= 500:
        return None
    return weight, reps


def format_result(weight: float, reps: list[int]) -> str:
    reps_text = ", ".join(map(str, reps))
    return f"{fmt(weight)} кг × {reps_text}" if weight else f"{reps_text} повт."


def rep_range(planned: str) -> tuple[int, int] | None:
    nums = [int(n) for n in re.findall(r"\d+", planned)[:2]]
    return (min(nums), max(nums)) if nums else None


def advice(planned_reps: str, planned_sets: int, weight: float, reps: list[int]) -> str:
    """Double progression: fill the top of the rep range in every set, then add weight."""
    rng = rep_range(planned_reps)
    if not rng or not reps:
        return ""
    lo, hi = rng
    if len(reps) >= planned_sets and min(reps) >= hi:
        if weight:
            step = 2.5 if weight >= 20 else 1
            return f"🔼 В прошлый раз всё сделано — сегодня пробуй {fmt(weight + step)} кг"
        return "🔼 В прошлый раз всё сделано — добавь 1–2 повтора в подход или утяжеление"
    if min(reps) < lo:
        if weight:
            lighter = max(round(weight * 0.9 / 2.5) * 2.5, 0)
            return f"↔️ Оставайся на {fmt(weight)} кг, а если тяжело — сбавь до {fmt(lighter)} кг"
        return "↔️ Пока не повышай нагрузку, добивай повторы"
    target = f"{fmt(weight)} кг" if weight else "этой нагрузке"
    return f"↔️ Оставайся на {target} и добивай до {hi} повторов в каждом подходе"
