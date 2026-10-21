from datetime import datetime

from config import TIMEZONE

SPARKS = "▁▂▃▄▅▆▇█"


def now() -> datetime:
    return datetime.now(TIMEZONE)


def today() -> str:
    return now().date().isoformat()


def fmt(x: float) -> str:
    """62.5 -> '62.5', 60.0 -> '60'."""
    return f"{x:.1f}".rstrip("0").rstrip(".")


def plural(n: int, one: str, few: str, many: str) -> str:
    """plural(21, 'год', 'года', 'лет') -> '21 год'."""
    if n % 10 == 1 and n % 100 != 11:
        word = one
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        word = few
    else:
        word = many
    return f"{n} {word}"


def short_date(iso: str) -> str:
    return f"{iso[8:10]}.{iso[5:7]}"


def sparkline(values: list[float]) -> str:
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    if hi == lo:
        return SPARKS[3] * len(values)
    return "".join(SPARKS[round((v - lo) / (hi - lo) * (len(SPARKS) - 1))] for v in values)


def split_text(text: str, limit: int = 3500) -> list[str]:
    """Split into Telegram-sized chunks, preferring paragraph and line breaks."""
    chunks = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks
