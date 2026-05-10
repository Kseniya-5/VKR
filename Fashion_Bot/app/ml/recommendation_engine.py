from __future__ import annotations

import json
from typing import Any


LABEL_RU = {
    # item
    "accessory": "аксессуар",
    "ankle boot": "ботильоны",
    "bag": "сумка",
    "beanie": "шапка",
    "belt": "ремень",
    "boot": "ботинки",
    "dress": "платье",
    "glove": "перчатки",
    "hat": "головной убор",
    "jacket": "куртка",
    "jean": "джинсы",
    "jewelry": "украшения",
    "jogger": "джоггеры",
    "leather jacket": "кожаная куртка",
    "legging": "леггинсы",
    "pant": "брюки",
    "scarf": "шарф",
    "shirt dress": "платье-рубашка",
    "shoe": "обувь",
    "sneaker": "кроссовки",
    "sock": "носки",
    "sweater": "свитер",
    "trouser": "брюки",
    # colors
    "black": "чёрный",
    "blue": "синий",
    "brown": "коричневый",
    "dark": "тёмный",
    "grey": "серый",
    "grid": "клетка",
    "heather": "меланж",
    "neon": "неоновый",
    "plaid": "клетчатый",
    "silver": "серебристый",
    "wash": "варёный деним",
    "white": "белый",
    "with": "комбинированный",
    "yellow": "жёлтый",
    # style
    "athleisure": "спорт-шик",
    "bohemian": "богемный",
    "boho": "бохо",
    "boho chic": "бохо-шик",
    "casual": "кэжуал",
    "edgy": "смелый стиль",
    "grunge": "гранж",
    "minimalist": "минимализм",
    "outdoor": "прогулочный стиль",
    "street style": "стритстайл",
    "streetwear": "стритвир",
    # season
    "all - season": "любой сезон",
    "fall": "осень",
    "winter": "зима",
}


def ru_label(value: Any) -> str:
    if value is None:
        return "не определено"
    raw = str(value).strip()
    if not raw:
        return "не определено"
    return LABEL_RU.get(raw.lower(), raw)


def ru_list(values: list[str] | None, limit: int = 4) -> str:
    cleaned = [ru_label(v) for v in (values or []) if v]
    if not cleaned:
        return "не определено"
    return ", ".join(cleaned[:limit])


def first(values: list[str] | None, fallback: str = "") -> str:
    return str(values[0]) if values else fallback


def _parse_tags(tags: Any) -> dict[str, list[str]]:
    if isinstance(tags, dict):
        return tags
    if isinstance(tags, str) and tags.strip():
        try:
            data = json.loads(tags)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _candidate_label(photo: dict[str, Any]) -> str:
    tags = _parse_tags(photo.get("tags"))
    item = photo.get("item_type") or first(tags.get("item"), "вещь")
    color = photo.get("color") or first(tags.get("color"), "")
    style = photo.get("style") or first(tags.get("style"), "")

    parts = [ru_label(item)]
    if color:
        parts.append(ru_label(color))
    if style:
        parts.append(ru_label(style))
    return " / ".join(parts)


def _score_candidate(photo: dict[str, Any], predictions: dict[str, list[str]]) -> int:
    tags = _parse_tags(photo.get("tags"))
    score = 0
    item = photo.get("item_type") or first(tags.get("item"), "")
    color = photo.get("color") or first(tags.get("color"), "")
    style = photo.get("style") or first(tags.get("style"), "")
    season = photo.get("season") or first(tags.get("season"), "")

    if item and item not in predictions.get("item", []):
        score += 2
    if color and color in predictions.get("color", []):
        score += 2
    if style and style in predictions.get("style", []):
        score += 2
    if season and season in predictions.get("season", []):
        score += 1
    return score


def top_candidates(predictions: dict[str, list[str]], candidates: list[dict[str, Any]] | None, limit: int = 3) -> list[dict[str, Any]]:
    ranked = sorted(candidates or [], key=lambda p: _score_candidate(p, predictions), reverse=True)
    return [p for p in ranked if _score_candidate(p, predictions) > 0][:limit]


def candidates_for_prompt(predictions: dict[str, list[str]], candidates: list[dict[str, Any]] | None, limit: int = 6) -> list[str]:
    return [_candidate_label(p) for p in top_candidates(predictions, candidates, limit=limit)]


def build_recommendation_text(
    predictions: dict[str, list[str]],
    *,
    model_type: str,
    candidates: list[dict[str, Any]] | None = None,
    raw: dict[str, Any] | None = None,
) -> str:
    """Локальный fallback, если Vision API не задан или недоступен."""
    matched = candidates_for_prompt(predictions, candidates, limit=3)

    lines = [
        "👗 <b>Рекомендация готова</b>",
        f"🤖 Модель: <b>{model_type}</b>",
        "",
        "🔎 <b>CV-модель определила:</b>",
        f"• Вещь: {ru_list(predictions.get('item'), 3)}",
        f"• Цвет: {ru_list(predictions.get('color'), 3)}",
        f"• Стиль: {ru_list(predictions.get('style'), 3)}",
        f"• Сезон: {ru_list(predictions.get('season'), 2)}",
        "",
        "✨ <b>Как дополнить образ:</b>",
        "• Оставьте один главный акцент: цвет, фактуру или аксессуар.",
        "• Поддержите палитру обувью, сумкой или верхним слоем.",
        "• Если образ уже активный, добавьте спокойную базу без лишнего принта.",
    ]

    if matched:
        lines.extend(["", "🧩 <b>Можно попробовать из гардероба:</b>"])
        lines.extend(f"• {item}" for item in matched)

    lines.extend(["", "ℹ️ Vision API не использовался, поэтому совет основан только на CV-признаках."])
    return "\n".join(lines)


def build_outfit_text(
    predictions: dict[str, list[str]],
    *,
    model_type: str,
    candidates: list[dict[str, Any]] | None = None,
    raw: dict[str, Any] | None = None,
) -> str:
    """Локальный fallback, если Vision API не задан или недоступен."""
    matched = candidates_for_prompt(predictions, candidates, limit=4)

    lines = [
        "🧥 <b>Образ собран</b>",
        f"🤖 Модель: <b>{model_type}</b>",
        "",
        "🔎 <b>Основа:</b>",
        f"• Вещь: {ru_list(predictions.get('item'), 3)}",
        f"• Палитра: {ru_list(predictions.get('color'), 3)}",
        f"• Стиль: {ru_list(predictions.get('style'), 3)}",
        "",
        "👕 <b>Конкретный вариант:</b>",
        "• База: выбранная вещь + спокойный низ или верх.",
        "• Обувь: нейтральная пара, чтобы не спорить с главным элементом.",
        "• Акцент: сумка, ремень или украшение в одном из цветов образа.",
    ]

    if matched:
        lines.extend(["", "🧩 <b>Что можно добавить из гардероба:</b>"])
        lines.extend(f"• {item}" for item in matched)

    lines.extend(["", "ℹ️ Vision API не использовался, поэтому комплект основан только на CV-признаках."])
    return "\n".join(lines)
