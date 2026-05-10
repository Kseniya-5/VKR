from __future__ import annotations

import base64
import io
import json
import os
import re
from pathlib import Path
from typing import Any

import aiohttp
from PIL import Image

from app.core.config import settings
from app.ml.recommendation_engine import candidates_for_prompt, ru_list


class VisionAdvisorError(RuntimeError):
    pass


def _provider() -> str:
    return (getattr(settings, "vision_provider", "openwebui") or "openwebui").strip().lower()


def _enabled() -> bool:
    if not bool(getattr(settings, "vision_api_enabled", True)):
        return False

    provider = _provider()
    if provider in {"disabled", "none", "off", "false", "0"}:
        return False

    if provider == "openwebui":
        return bool(getattr(settings, "openwebui_api_url", None) or os.getenv("API_URL"))

    if provider == "openai":
        return bool(getattr(settings, "openai_api_key", None))

    return True


def _image_to_data_url(image_path: str | Path) -> str:
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Файл фото не найден: {path}")

    with Image.open(path) as img:
        img = img.convert("RGB")
        max_side = int(getattr(settings, "vision_image_max_side", 1280) or 1280)
        if max(img.size) > max_side:
            img.thumbnail((max_side, max_side))

        buffer = io.BytesIO()
        quality = int(getattr(settings, "vision_image_jpeg_quality", 85) or 85)
        img.save(buffer, format="JPEG", quality=quality, optimize=True)

    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _extract_openai_responses_text(payload: dict[str, Any]) -> str:
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]

    texts: list[str] = []
    for item in payload.get("output", []) or []:
        for content in item.get("content", []) or []:
            if isinstance(content.get("text"), str):
                texts.append(content["text"])
            elif isinstance(content.get("output_text"), str):
                texts.append(content["output_text"])
    return "\n".join(texts).strip()


def _extract_chat_completion_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices") or []
    if not choices:
        return ""

    message = choices[0].get("message") or {}
    content = message.get("content")

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        texts: list[str] = []
        for part in content:
            if isinstance(part, dict):
                if isinstance(part.get("text"), str):
                    texts.append(part["text"])
                elif isinstance(part.get("content"), str):
                    texts.append(part["content"])
        return "\n".join(texts).strip()

    return ""


def _parse_jsonish(text: str) -> dict[str, Any]:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        data = json.loads(cleaned)
        return data if isinstance(data, dict) else {"text": cleaned}
    except Exception:
        pass

    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            return data if isinstance(data, dict) else {"text": cleaned}
        except Exception:
            pass

    return {"text": cleaned}


def _normalize_ru_text(text: str) -> str:
    """Небольшая страховка от частых ошибок локальной модели."""
    text = (text or "").strip()

    replacements = {
        "ботинги": "ботинки",
        "ботинги": "ботинки",
        "ботингами": "ботинками",
        "ботингов": "ботинок",
        "minimalistic": "минималистичный",
        "minimalist": "минималистичный",
        "casual": "повседневный",
        "street style": "стритстайл",
        "streetwear": "стритвир",
    }
    for bad, good in replacements.items():
        text = re.sub(bad, good, text, flags=re.IGNORECASE)

    # Убираем слишком частое повторение одной и той же фразы.
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _trim_for_telegram(text: str, limit: int = 950) -> str:
    text = _normalize_ru_text(text)
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit("\n", 1)[0].strip()
    return cut or text[:limit].strip()


def _system_prompt(mode: str) -> str:
    base = (
        "Ты fashion-стилист в Telegram-боте. Фото уже прошло отдельную проверку на наличие одежды, "
        "поэтому твоя задача — внимательно смотреть на изображение и писать полезный fashion-ответ. "
        "CV-признаки item/color/style/season используй только как черновую подсказку: они могут сильно ошибаться. "
        "Главный источник правды — само фото. Не придумывай вещи, которых не видно. "
        "Не описывай лицо, возраст, фигуру, тело или привлекательность человека. "
        "Пиши только про одежду, обувь, сумки, аксессуары, цвета, стиль и практичные сочетания. "
        "Пиши полностью на русском. Запрещённые слова: 'ботинги', 'minimalistic', 'casual' в английском виде. "
        "Правильно: 'ботинки', 'минималистичный', 'повседневный'. "
        "Используй Telegram HTML: <b>...</b>. Не используй Markdown. "
        "Ответ должен быть коротким, до 850 символов. "
        "Верни строго JSON без markdown: "
        "{\"is_fashion_photo\": true, \"corrected\": {\"item\": [], \"color\": [], \"style\": [], \"season\": []}, \"text\": \"...\"}."
    )

    if mode == "outfit":
        return (
            base
            + " Раздел: СОБРАТЬ ОБРАЗ. Дай конкретный комплект, а не общие советы. "
              "Формат текста: <b>Вариант 1</b> и <b>Вариант 2</b>. "
              "В каждом варианте назови конкретно: слой/верх/низ, обувь, сумку или аксессуар, цветовую логику. "
              "Если на фото уже готовый образ, предложи, что оставить и одну понятную альтернативу."
        )

    return (
        base
        + " Раздел: РЕКОМЕНДАЦИИ. Не собирай новый образ с нуля. "
          "Дай 3 коротких практичных пункта: 1) что оставить главным акцентом, "
          "2) чем дополнить, 3) чего не перегружать. "
          "Совет должен улучшать текущий образ."
    )


def _user_prompt(
    *,
    mode: str,
    predictions: dict[str, list[str]],
    model_type: str,
    candidates: list[dict[str, Any]] | None,
) -> str:
    matched = candidates_for_prompt(predictions, candidates, limit=6)
    if mode == "outfit":
        task = (
            "Собери конкретный образ по фото. Не пиши общие фразы вроде 'добавьте аксессуары'; "
            "называй конкретно: обувь, сумка, слой, цвет, аксессуар."
        )
    else:
        task = (
            "Дай короткие рекомендации, как улучшить уже имеющийся образ на фото. "
            "Не заменяй образ полностью и не собирай новый комплект с нуля."
        )

    return (
        f"Задача: {task}\n\n"
        f"CV-модель: {model_type}\n"
        "CV-признаки ниже могут быть ошибочными. Проверь их по фото и исправь молча:\n"
        f"- вещь: {ru_list(predictions.get('item'), 5)}\n"
        f"- цвет: {ru_list(predictions.get('color'), 5)}\n"
        f"- стиль: {ru_list(predictions.get('style'), 5)}\n"
        f"- сезон: {ru_list(predictions.get('season'), 3)}\n\n"
        "Кандидаты из гардероба пользователя, если они нужны для комплекта:\n"
        + ("\n".join(f"- {x}" for x in matched) if matched else "- пока нет подходящих распознанных вещей")
    )


def _normalize_openwebui_url(raw_url: str) -> str:
    url = raw_url.strip().rstrip("/")
    if url.endswith("/api/chat/completions") or url.endswith("/v1/chat/completions"):
        return url
    return f"{url}/api/chat/completions"


def _bool_from_result(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1", "да"}:
            return True
        if lowered in {"false", "no", "0", "нет"}:
            return False
    return None


async def _call_openwebui_chat_completions(
    *,
    image_url: str,
    mode: str,
    predictions: dict[str, list[str]],
    model_type: str,
    candidates: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    api_url = (
        getattr(settings, "openwebui_api_url", None)
        or os.getenv("OPENWEBUI_API_URL")
        or os.getenv("OLLAMA_VISION_API_URL")
        or os.getenv("API_URL")
    )
    if not api_url:
        raise VisionAdvisorError("OPENWEBUI_API_URL/API_URL не задан")

    model = (
        getattr(settings, "openwebui_model", None)
        or os.getenv("OPENWEBUI_MODEL")
        or os.getenv("OLLAMA_VISION_MODEL")
        or os.getenv("VISION_MODEL")
        or "llama3.2-vision:latest"
    )

    api_key = (
        getattr(settings, "openwebui_api_key", None)
        or os.getenv("OPENWEBUI_API_KEY")
        or os.getenv("OLLAMA_VISION_API_KEY")
        or os.getenv("API_KEY")
        or ""
    )
    api_key = str(api_key).strip().strip('"').strip("'")

    auth_header = (
        getattr(settings, "openwebui_auth_header", None)
        or os.getenv("OPENWEBUI_AUTH_HEADER")
        or "Authorization"
    )
    auth_header = str(auth_header).strip()

    headers = {"Content-Type": "application/json"}
    if api_key:
        if auth_header.lower() in {"authorization", "bearer"}:
            headers["Authorization"] = f"Bearer {api_key}"
        else:
            headers[auth_header] = api_key

    timeout = aiohttp.ClientTimeout(
        total=int(getattr(settings, "vision_api_timeout_seconds", 120) or 120)
    )

    async def post_openwebui(payload: dict[str, Any]) -> dict[str, Any]:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                _normalize_openwebui_url(api_url),
                headers=headers,
                json=payload,
            ) as resp:
                body = await resp.text()
                if resp.status >= 400:
                    raise VisionAdvisorError(
                        f"Open WebUI Vision API вернул status={resp.status}: {body[:1000]}"
                    )
                return json.loads(body)

    default_non_fashion_text = (
        "😔 На фото не видно одежды или образа.\n\n"
        "Пожалуйста, выберите фото с вещью, обувью, аксессуаром или готовым образом."
    )

    # Этап 1. Очень консервативная проверка фото БЕЗ CV-признаков.
    # Важно: если модель сомневается, она должна вернуть true, чтобы не отсекать настоящие фото одежды.
    validation_prompt = (
        "You are a conservative visual gatekeeper for a fashion app. Look ONLY at the image.\n"
        "Return strict JSON only, no markdown.\n\n"
        "Question: can this image be used for fashion advice?\n"
        "Return false ONLY if the image clearly contains no clothing, no shoes, no bag, no belt, "
        "no jewelry, no hat, no glasses, no fashion accessory, no textile garment, and no person wearing clothes.\n"
        "Return true if at least one visible clothing item, shoe, bag, accessory, textile garment, "
        "or a person wearing an outfit is present, even partially.\n"
        "If you are uncertain, return true.\n"
        "Flowers, food, animals, landscape, interior, cosmetics without clothes/accessories = false.\n\n"
        "JSON schema: {\"is_fashion_photo\": true/false, \"reason\": \"short reason\"}\n\n"
        "[Image Attached]"
    )

    validation_value: bool | None = None
    try:
        validation_payload = {
            "model": model,
            "stream": False,
            "temperature": 0,
            "messages": [
                {
                    "role": "user",
                    "content": validation_prompt,
                    "images": [image_url],
                }
            ],
        }
        validation_data = await post_openwebui(validation_payload)
        validation_text = _extract_chat_completion_text(validation_data)
        validation_parsed = _parse_jsonish(validation_text)
        validation_value = _bool_from_result(validation_parsed.get("is_fashion_photo"))
    except Exception:
        # Если проверка сломалась, не блокируем пользователя: переходим к основному совету.
        validation_value = None

    if validation_value is False:
        return {
            "text": default_non_fashion_text,
            "is_fashion_photo": False,
            "corrected": None,
            "vision_model": model,
            "vision_provider": "openwebui",
        }

    # Этап 2. Основной fashion-ответ. Здесь CV-признаки уже можно дать как подсказку.
    user_prompt = _user_prompt(
        mode=mode,
        predictions=predictions,
        model_type=model_type,
        candidates=candidates,
    )

    advice_payload = {
        "model": model,
        "stream": False,
        "temperature": 0.1,
        "messages": [
            {
                "role": "user",
                "content": f"{_system_prompt(mode)}\n\n{user_prompt}\n\n[Image Attached]",
                "images": [image_url],
            }
        ],
    }

    data = await post_openwebui(advice_payload)
    output_text = _extract_chat_completion_text(data)
    if not output_text:
        raise VisionAdvisorError(
            f"Open WebUI вернул пустой content: {json.dumps(data, ensure_ascii=False)[:1000]}"
        )

    parsed = _parse_jsonish(output_text)
    text = _trim_for_telegram(str(parsed.get("text") or output_text))
    if not text:
        raise VisionAdvisorError("Open WebUI вернул пустой текст")

    # Если предварительная проверка не сказала false, не позволяем второму запросу случайно
    # превратить фото одежды в отказ. Это частая ошибка llama3.2-vision на сложных кадрах.
    lowered_text = text.lower()
    if validation_value is not False and (
        "не видно одежды" in lowered_text or "нет одежды" in lowered_text or "no clothing" in lowered_text
    ):
        raise VisionAdvisorError("Open WebUI вернул отказ после успешной/неопределённой проверки fashion-photo")

    return {
        "text": text,
        "is_fashion_photo": True,
        "corrected": parsed.get("corrected") if isinstance(parsed.get("corrected"), dict) else None,
        "vision_model": model,
        "vision_provider": "openwebui",
    }


async def _call_openai_responses(
    *,
    image_url: str,
    mode: str,
    predictions: dict[str, list[str]],
    model_type: str,
    candidates: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    api_key = getattr(settings, "openai_api_key", None)
    if not api_key:
        raise VisionAdvisorError("OPENAI_API_KEY не задан")

    model = getattr(settings, "openai_vision_model", None) or "gpt-5-mini"
    request_payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [{"type": "input_text", "text": _system_prompt(mode)}],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": _user_prompt(
                            mode=mode,
                            predictions=predictions,
                            model_type=model_type,
                            candidates=candidates,
                        ),
                    },
                    {"type": "input_image", "image_url": image_url},
                ],
            },
        ],
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    timeout = aiohttp.ClientTimeout(total=int(settings.vision_api_timeout_seconds or 45))
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post("https://api.openai.com/v1/responses", headers=headers, json=request_payload) as resp:
            body = await resp.text()
            if resp.status >= 400:
                raise VisionAdvisorError(f"OpenAI Vision API вернул status={resp.status}: {body[:1000]}")
            data = json.loads(body)

    output_text = _extract_openai_responses_text(data)
    parsed = _parse_jsonish(output_text)
    is_fashion_photo = _bool_from_result(parsed.get("is_fashion_photo"))

    default_non_fashion_text = (
        "😔 На фото не видно одежды или образа.\n\n"
        "Пожалуйста, выберите фото с вещью, обувью, аксессуаром или готовым образом."
    )

    if is_fashion_photo is False:
        return {
            "text": _trim_for_telegram(str(parsed.get("text") or default_non_fashion_text), limit=600),
            "is_fashion_photo": False,
            "corrected": None,
            "vision_model": model,
            "vision_provider": "openai",
        }

    text = _trim_for_telegram(str(parsed.get("text") or output_text))
    if not text:
        raise VisionAdvisorError("OpenAI Vision API вернул пустой текст")

    return {
        "text": text,
        "is_fashion_photo": True if is_fashion_photo is None else is_fashion_photo,
        "corrected": parsed.get("corrected") if isinstance(parsed.get("corrected"), dict) else None,
        "vision_model": model,
        "vision_provider": "openai",
    }


async def build_vision_fashion_text(
    *,
    image_path: str | Path,
    mode: str,
    predictions: dict[str, list[str]],
    raw: dict[str, Any] | None,
    model_type: str,
    candidates: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    """Возвращает человекочитаемый совет от Vision API или None, если API выключен."""
    if not _enabled():
        return None

    image_url = _image_to_data_url(image_path)
    provider = _provider()

    if provider == "openwebui":
        return await _call_openwebui_chat_completions(
            image_url=image_url,
            mode=mode,
            predictions=predictions,
            model_type=model_type,
            candidates=candidates,
        )

    if provider == "openai":
        return await _call_openai_responses(
            image_url=image_url,
            mode=mode,
            predictions=predictions,
            model_type=model_type,
            candidates=candidates,
        )

    raise VisionAdvisorError(f"Неизвестный VISION_PROVIDER={provider!r}. Используйте openwebui, openai или disabled.")
