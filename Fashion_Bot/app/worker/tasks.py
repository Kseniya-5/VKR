from __future__ import annotations

import asyncio
import json
import shutil
import traceback
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

import aiohttp
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.worker.celery_app import celery_app


MEDIA_ROOT = Path(getattr(settings, "media_root", "/app/media"))


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_session_factory():
    engine = create_async_engine(settings.database_url, future=True, pool_pre_ping=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, session_factory


async def _set_task_status(session_factory, task_id: str, status: str, result: dict[str, Any] | None = None) -> None:
    async with session_factory() as session:
        await session.execute(
            text(
                """
                UPDATE model_tasks
                SET status = :status,
                    result = :result,
                    updated_at = CURRENT_TIMESTAMP
                WHERE task_id = :task_id
                """
            ),
            {
                "task_id": task_id,
                "status": status,
                "result": json.dumps(result, ensure_ascii=False) if result is not None else None,
            },
        )
        await session.commit()


async def _get_task_result_payload(session_factory, task_id: str) -> dict[str, Any]:
    async with session_factory() as session:
        result = await session.execute(
            text(
                """
                SELECT result
                FROM model_tasks
                WHERE task_id = :task_id
                LIMIT 1
                """
            ),
            {"task_id": task_id},
        )
        row = result.mappings().first()

    if not row or not row["result"]:
        return {}

    try:
        return json.loads(row["result"])
    except Exception:
        return {}


async def _fetch_photo(session_factory, user_id: str, photo_id: str) -> dict[str, Any]:
    async with session_factory() as session:
        result = await session.execute(
            text(
                """
                SELECT id, user_id, original_path, telegram_file_id, is_active
                FROM user_photos
                WHERE id = :photo_id
                  AND user_id = :user_id
                LIMIT 1
                """
            ),
            {"photo_id": photo_id, "user_id": user_id},
        )
        row = result.mappings().first()

    if not row:
        raise RuntimeError("Фото не найдено")
    if not row["is_active"]:
        raise RuntimeError("Фото было удалено")
    if not row["original_path"]:
        raise RuntimeError("У фото отсутствует путь к файлу")
    return dict(row)


async def _fetch_candidate_photos(session_factory, user_id: str, exclude_photo_id: str, limit: int = 30) -> list[dict[str, Any]]:
    async with session_factory() as session:
        result = await session.execute(
            text(
                """
                SELECT
                    id,
                    original_path,
                    telegram_file_id,
                    item_type,
                    color,
                    season,
                    style,
                    tags,
                    created_at
                FROM user_photos
                WHERE user_id = :user_id
                  AND id <> :exclude_photo_id
                  AND is_active = TRUE
                  AND original_path IS NOT NULL
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"user_id": user_id, "exclude_photo_id": exclude_photo_id, "limit": limit},
        )
        return [dict(row) for row in result.mappings().all()]


async def _update_photo_attributes(session_factory, photo_id: str, predictions: dict[str, list[str]]) -> None:
    def first(values: list[str] | None) -> str | None:
        return values[0] if values else None

    async with session_factory() as session:
        await session.execute(
            text(
                """
                UPDATE user_photos
                SET item_type = :item_type,
                    color = :color,
                    season = :season,
                    style = :style,
                    tags = :tags,
                    processing_status = 'ready',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = :photo_id
                """
            ),
            {
                "photo_id": photo_id,
                "item_type": first(predictions.get("item")),
                "color": first(predictions.get("color")),
                "season": first(predictions.get("season")),
                "style": first(predictions.get("style")),
                "tags": json.dumps(predictions, ensure_ascii=False),
            },
        )
        await session.commit()


def _attrs_missing(photo: dict[str, Any]) -> bool:
    return not any([photo.get("item_type"), photo.get("color"), photo.get("season"), photo.get("style")])


async def _ensure_candidate_attributes(
    session_factory,
    candidates: list[dict[str, Any]],
    *,
    model_type: str,
    limit: int,
) -> list[dict[str, Any]]:
    from app.ml.fashion_attributes import predict_attributes

    updated: list[dict[str, Any]] = []
    classified_count = 0

    for photo in candidates:
        current = dict(photo)
        if _attrs_missing(current) and classified_count < limit:
            try:
                image_path = MEDIA_ROOT / str(current["original_path"])
                if not image_path.exists():
                    current["classification_error"] = "file_not_found"
                    updated.append(current)
                    continue

                predictions, _raw, normalized_model = predict_attributes(
                    str(image_path),
                    models_root=settings.ml_models_root,
                    model_type=model_type,
                    threshold=settings.ml_prediction_threshold,
                )
                await _update_photo_attributes(session_factory, str(current["id"]), predictions)
                current["item_type"] = (predictions.get("item") or [None])[0]
                current["color"] = (predictions.get("color") or [None])[0]
                current["season"] = (predictions.get("season") or [None])[0]
                current["style"] = (predictions.get("style") or [None])[0]
                current["tags"] = json.dumps(predictions, ensure_ascii=False)
                current["classified_by"] = normalized_model
                classified_count += 1
            except Exception:
                current["classification_error"] = traceback.format_exc()
        updated.append(current)

    return updated


async def _build_final_text(
    *,
    image_path: Path,
    mode: str,
    predictions: dict[str, list[str]],
    raw_predictions: dict[str, Any],
    normalized_model: str,
    candidates: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    from app.ml.recommendation_engine import build_outfit_text, build_recommendation_text
    from app.ml.vision_advisor import build_vision_fashion_text

    local_text = (
        build_outfit_text(predictions=predictions, raw=raw_predictions, model_type=normalized_model, candidates=candidates)
        if mode == "outfit"
        else build_recommendation_text(predictions=predictions, raw=raw_predictions, model_type=normalized_model, candidates=candidates)
    )

    meta: dict[str, Any] = {"vision_used": False}
    try:
        vision_result = await build_vision_fashion_text(
            image_path=image_path,
            mode=mode,
            predictions=predictions,
            raw=raw_predictions,
            model_type=normalized_model,
            candidates=candidates,
        )
        if vision_result and vision_result.get("text"):
            is_fashion_photo = vision_result.get("is_fashion_photo")
            meta.update({
                "vision_used": True,
                "vision_model": vision_result.get("vision_model"),
                "vision_provider": vision_result.get("vision_provider"),
                "corrected_predictions": vision_result.get("corrected"),
                "is_fashion_photo": is_fashion_photo,
                "validation": vision_result.get("validation"),
            })
            if is_fashion_photo is False:
                meta["not_fashion_photo"] = True
            return str(vision_result["text"]), meta
    except Exception as exc:
        meta.update({"vision_error": str(exc), "vision_traceback": traceback.format_exc()})

    return local_text, meta


async def _fetch_telegram_id(session_factory, user_id: str) -> int | None:
    async with session_factory() as session:
        result = await session.execute(
            text(
                """
                SELECT telegram_id
                FROM telegram_accounts
                WHERE user_id = :user_id
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
        row = result.mappings().first()
    if not row:
        return None
    try:
        return int(row["telegram_id"])
    except Exception:
        return None


def _telegram_main_menu_reply_markup() -> dict[str, Any]:
    """Inline-кнопки должны совпадать с Telegram start_keyboard(is_registered=True)."""
    return {
        "inline_keyboard": [
            [
                {"text": "❔ Помощь", "callback_data": "open_help"},
                {"text": "⚙️ Управление аккаунтом", "callback_data": "account_management"},
            ],
            [
                {"text": "👤 Профиль", "callback_data": "open_profile"},
                {"text": "🔗 Связать с веб-версией", "callback_data": "link_web"},
            ],
            [
                {"text": "📸 Загрузить фото", "callback_data": "upload_photo"},
                {"text": "🖼 Посмотреть фото", "callback_data": "view_photos"},
            ],
            [
                {"text": "👗 Получить рекомендации", "callback_data": "get_recommendations"},
                {"text": "🧥 Собрать образ", "callback_data": "build_outfit"},
            ],
        ]
    }


def _strip_html_to_short_text(text_value: str, limit: int = 900) -> str:
    text_value = text_value or ""
    if len(text_value) <= limit:
        return text_value
    return text_value[:limit].rsplit("\n", 1)[0].strip() or text_value[:limit]


async def _telegram_api_call(method: str, payload: dict[str, Any] | None = None, files: dict[str, Any] | None = None) -> dict[str, Any] | None:
    token = getattr(settings, "bot_token", None)
    if not token:
        return None

    url = f"https://api.telegram.org/bot{token}/{method}"
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        if files:
            form = aiohttp.FormData()
            for key, value in (payload or {}).items():
                if isinstance(value, (dict, list)):
                    form.add_field(key, json.dumps(value, ensure_ascii=False))
                else:
                    form.add_field(key, str(value))
            for key, file_obj in files.items():
                form.add_field(key, file_obj, filename=getattr(file_obj, "name", "photo.jpg"), content_type="image/jpeg")
            async with session.post(url, data=form) as resp:
                text_body = await resp.text()
                if resp.status >= 400:
                    raise RuntimeError(f"Telegram API {method} status={resp.status}: {text_body[:1000]}")
                return json.loads(text_body)
        async with session.post(url, json=payload or {}) as resp:
            text_body = await resp.text()
            if resp.status >= 400:
                raise RuntimeError(f"Telegram API {method} status={resp.status}: {text_body[:1000]}")
            return json.loads(text_body)


async def _send_telegram_web_processing_message(
    session_factory,
    *,
    user_id: str,
    mode: str,
) -> dict[str, Any]:
    telegram_id = await _fetch_telegram_id(session_factory, user_id)
    if not telegram_id:
        return {"telegram_notified": False, "reason": "telegram_not_linked"}

    if mode == "outfit":
        text_value = (
            "🧥 <b>Сбор образа из веб-версии</b>\n\n"
            "⏳ Фото принято в работу. Собираю образ и скоро пришлю результат."
        )
    else:
        text_value = (
            "👗 <b>Рекомендации из веб-версии</b>\n\n"
            "⏳ Фото принято в работу. Готовлю рекомендации и скоро пришлю результат."
        )

    try:
        response = await _telegram_api_call(
            "sendMessage",
            payload={
                "chat_id": telegram_id,
                "text": text_value,
                "parse_mode": "HTML",
            },
        )
        message_id = None
        if response and response.get("ok") and isinstance(response.get("result"), dict):
            message_id = response["result"].get("message_id")
        return {
            "telegram_notified": True,
            "chat_id": telegram_id,
            "processing_message_id": message_id,
            "processing_message_sent": bool(message_id),
        }
    except Exception as exc:
        return {
            "telegram_notified": False,
            "chat_id": telegram_id,
            "telegram_notify_error": str(exc),
        }


async def _notify_telegram_about_web_result(
    session_factory,
    *,
    user_id: str,
    photo_id: str,
    image_path: Path | None,
    mode: str,
    result_text: str,
    ok: bool,
    processing_message_id: int | None = None,
) -> dict[str, Any]:
    telegram_id = await _fetch_telegram_id(session_factory, user_id)
    if not telegram_id:
        return {"telegram_notified": False, "reason": "telegram_not_linked"}

    sent: dict[str, Any] = {
        "telegram_notified": True,
        "chat_id": telegram_id,
        "processing_message_id": processing_message_id,
    }

    result_message_text = _strip_html_to_short_text(result_text, 3500)
    menu_text = (
        "🏠 <b>Главное меню Fashion Bot!</b>\n\n"
        "Результат можно увидеть выше и в истории веб-версии.\n\n"
        "Выберите нужное действие ниже."
    )
    if not ok:
        menu_text = (
            "🏠 <b>Главное меню Fashion Bot!</b>\n\n"
            "Сообщение об ошибке можно увидеть выше и в истории веб-версии.\n\n"
            "Выберите нужное действие ниже."
        )

    try:
        if processing_message_id:
            await _telegram_api_call(
                "editMessageText",
                payload={
                    "chat_id": telegram_id,
                    "message_id": processing_message_id,
                    "text": result_message_text,
                    "parse_mode": "HTML",
                },
            )
            sent["result_message_edited"] = True
        else:
            # Fallback: если задача была запущена до нового кода или служебное сообщение не отправилось.
            response = await _telegram_api_call(
                "sendMessage",
                payload={
                    "chat_id": telegram_id,
                    "text": result_message_text,
                    "parse_mode": "HTML",
                },
            )
            sent["result_message_sent"] = True
            if response and response.get("ok") and isinstance(response.get("result"), dict):
                sent["result_message_id"] = response["result"].get("message_id")

        await _telegram_api_call(
            "sendMessage",
            payload={
                "chat_id": telegram_id,
                "text": menu_text,
                "parse_mode": "HTML",
                "reply_markup": _telegram_main_menu_reply_markup(),
            },
        )
        sent["main_menu_sent"] = True
    except Exception as exc:
        sent.update({"telegram_notified": False, "telegram_notify_error": str(exc)})
    return sent

async def _run_analysis(
    session_factory,
    task_id: str,
    user_id: str,
    photo_id: str,
    mode: str,
    model_type: str,
    source: str = "telegram",
) -> dict[str, Any]:
    from app.ml.fashion_attributes import predict_attributes

    mode = "outfit" if mode == "outfit" else "recommendation"
    source = "web" if source == "web" else "telegram"

    started_payload = {
        "message": "Задача запущена",
        "mode": mode,
        "model_type": model_type,
        "photo_id": photo_id,
        "source": source,
        "started_at": _utc_iso(),
    }
    await _set_task_status(session_factory, task_id, "STARTED", started_payload)

    web_processing_meta: dict[str, Any] = {}
    if source == "web":
        web_processing_meta = await _send_telegram_web_processing_message(
            session_factory,
            user_id=user_id,
            mode=mode,
        )
        started_payload["telegram_delivery"] = web_processing_meta
        await _set_task_status(session_factory, task_id, "STARTED", started_payload)

    photo = await _fetch_photo(session_factory, user_id=user_id, photo_id=photo_id)
    image_path = MEDIA_ROOT / str(photo["original_path"])
    if not image_path.exists():
        raise RuntimeError(f"Файл изображения не найден на диске: {image_path}")

    predictions, raw_predictions, normalized_model = predict_attributes(
        str(image_path),
        models_root=settings.ml_models_root,
        model_type=model_type,
        threshold=settings.ml_prediction_threshold,
    )

    await _update_photo_attributes(session_factory, photo_id=photo_id, predictions=predictions)

    candidates = await _fetch_candidate_photos(
        session_factory,
        user_id=user_id,
        exclude_photo_id=photo_id,
        limit=settings.ml_candidate_photo_limit,
    )
    candidates = await _ensure_candidate_attributes(
        session_factory,
        candidates,
        model_type=normalized_model,
        limit=settings.ml_auto_tag_candidates_limit,
    )

    text_result, advisor_meta = await _build_final_text(
        image_path=image_path,
        mode=mode,
        predictions=predictions,
        raw_predictions=raw_predictions,
        normalized_model=normalized_model,
        candidates=candidates,
    )

    title = "Идея образа" if mode == "outfit" else "Рекомендации"

    if advisor_meta.get("not_fashion_photo"):
        result = {
            "ok": False,
            "title": title,
            "mode": mode,
            "model_type": normalized_model,
            "photo_id": photo_id,
            "source": source,
            "error": "NOT_FASHION_PHOTO",
            "message": text_result,
            "predictions": predictions,
            "raw_predictions": raw_predictions,
            "text": text_result,
            "candidate_count": len(candidates),
            "advisor": advisor_meta,
            "finished_at": _utc_iso(),
        }
        if source == "web":
            notify_meta = await _notify_telegram_about_web_result(
                session_factory,
                user_id=user_id,
                photo_id=photo_id,
                image_path=None,
                mode=mode,
                result_text=text_result,
                ok=False,
                processing_message_id=web_processing_meta.get("processing_message_id"),
            )
            result["telegram_delivery"] = notify_meta
        await _set_task_status(session_factory, task_id, "FAILURE", result)
        return result

    result = {
        "ok": True,
        "title": title,
        "mode": mode,
        "model_type": normalized_model,
        "photo_id": photo_id,
        "source": source,
        "predictions": predictions,
        "raw_predictions": raw_predictions,
        "text": text_result,
        "candidate_count": len(candidates),
        "advisor": advisor_meta,
        "finished_at": _utc_iso(),
    }
    if source == "web":
        notify_meta = await _notify_telegram_about_web_result(
            session_factory,
            user_id=user_id,
            photo_id=photo_id,
            image_path=image_path,
            mode=mode,
            result_text=text_result,
            ok=True,
            processing_message_id=web_processing_meta.get("processing_message_id"),
        )
        result["telegram_delivery"] = notify_meta

    await _set_task_status(session_factory, task_id, "SUCCESS", result)
    return result


async def _run_analysis_with_own_engine(task_id: str, user_id: str, photo_id: str, mode: str, model_type: str, source: str = "telegram") -> dict[str, Any]:
    engine, session_factory = _make_session_factory()
    try:
        return await _run_analysis(session_factory, task_id, user_id, photo_id, mode, model_type, source)
    finally:
        await engine.dispose()


async def _set_failure_with_own_engine(task_id: str, user_id: str, mode: str, model_type: str, photo_id: str, source: str, exc: Exception) -> dict[str, Any]:
    engine, session_factory = _make_session_factory()
    try:
        error_code = "ML_MODEL_NOT_CONFIGURED" if type(exc).__name__ == "FashionModelNotConfigured" else type(exc).__name__
        text_result = (
            "😔 ML-модель пока не подключена.\n\n"
            f"Проверьте путь ML_MODELS_ROOT: {settings.ml_models_root}\n"
            "Для RandomForest нужны .joblib файлы, для ResNet — model.pt и *_mlb.json."
            if error_code == "ML_MODEL_NOT_CONFIGURED"
            else f"😔 Не удалось обработать фото.\n\nПричина: {str(exc)}"
        )
        result = {
            "ok": False,
            "mode": mode,
            "model_type": model_type,
            "photo_id": photo_id,
            "source": source,
            "error": error_code,
            "message": str(exc),
            "traceback": traceback.format_exc(),
            "text": text_result,
            "finished_at": _utc_iso(),
        }
        if source == "web":
            started_payload = await _get_task_result_payload(session_factory, task_id)
            delivery = started_payload.get("telegram_delivery") or {}
            notify_meta = await _notify_telegram_about_web_result(
                session_factory,
                user_id=user_id,
                photo_id=photo_id,
                image_path=None,
                mode=mode,
                result_text=text_result,
                ok=False,
                processing_message_id=delivery.get("processing_message_id"),
            )
            result["telegram_delivery"] = notify_meta
        await _set_task_status(session_factory, task_id, "FAILURE", result)
        return result
    finally:
        await engine.dispose()


@celery_app.task(name="app.worker.tasks.analyze_fashion_photo_task")
def analyze_fashion_photo_task(
    task_id: str,
    user_id: str,
    photo_id: str,
    mode: str = "recommendation",
    model_type: str = "RandomForest",
    source: str = "telegram",
) -> dict[str, Any]:
    try:
        return asyncio.run(_run_analysis_with_own_engine(task_id, user_id, photo_id, mode, model_type, source))
    except Exception as exc:
        return asyncio.run(_set_failure_with_own_engine(task_id, user_id, mode, model_type, photo_id, source, exc))


@celery_app.task(name="app.worker.tasks.cleanup_user_data_task")
def cleanup_user_data_task(*args: Any, **kwargs: Any) -> dict[str, Any]:
    user_id = kwargs.get("user_id")
    if user_id is None and args:
        user_id = args[0]
    if user_id is None:
        return {"success": False, "message": "user_id was not provided"}

    user_id = str(user_id)
    user_photos_dir = MEDIA_ROOT / "user_photos" / user_id
    removed_paths: list[str] = []
    if user_photos_dir.exists():
        shutil.rmtree(user_photos_dir, ignore_errors=True)
        removed_paths.append(str(user_photos_dir))
    return {"success": True, "user_id": user_id, "removed_paths": removed_paths}


async def _train_model_stub(task_id: str, model_params: dict[str, Any] | None = None) -> dict[str, Any]:
    engine, session_factory = _make_session_factory()
    try:
        result = {
            "ok": True,
            "message": "Training stub completed. Основной ML-функционал использует analyze_fashion_photo_task.",
            "model_params": model_params or {},
            "finished_at": _utc_iso(),
        }
        await _set_task_status(session_factory, task_id, "SUCCESS", result)
        return result
    finally:
        await engine.dispose()


@celery_app.task(name="app.worker.tasks.train_model_task")
def train_model_task(task_id: str, model_params: dict[str, Any] | None = None) -> dict[str, Any]:
    return asyncio.run(_train_model_stub(task_id=task_id, model_params=model_params))
