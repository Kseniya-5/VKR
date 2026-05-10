from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.db.models import User
from app.db.session import get_db


router = APIRouter(prefix="/fashion", tags=["fashion"])


class FashionAnalyzeRequest(BaseModel):
    photo_id: str
    mode: str = Field(default="recommendation", pattern="^(recommendation|outfit|rec)$")
    model_type: str = Field(default="RandomForest", pattern="^(RandomForest|ResNet|rf|resnet)$")


def _normalize_mode(mode: str) -> str:
    return "outfit" if mode == "outfit" else "recommendation"


def _normalize_model(model_type: str) -> str:
    lowered = model_type.strip().lower()
    if lowered in {"resnet", "res_net"}:
        return "ResNet"
    return "RandomForest"


def _safe_json_loads(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    try:
        data = json.loads(str(value))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


async def _ensure_photo_owner(db: AsyncSession, user_id: str, photo_id: str) -> None:
    result = await db.execute(
        text(
            """
            SELECT id
            FROM user_photos
            WHERE id = :photo_id
              AND user_id = :user_id
              AND is_active = TRUE
            LIMIT 1
            """
        ),
        {"photo_id": photo_id, "user_id": user_id},
    )
    if not result.mappings().first():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Фото не найдено или недоступно",
        )


@router.post("/analyze")
async def create_fashion_analysis(
    payload: FashionAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    user_id = str(current_user.id)
    photo_id = payload.photo_id
    mode = _normalize_mode(payload.mode)
    model_type = _normalize_model(payload.model_type)
    task_id = str(uuid4())

    await _ensure_photo_owner(db, user_id, photo_id)

    initial_result = {
        "ok": None,
        "source": "web",
        "mode": mode,
        "model_type": model_type,
        "photo_id": photo_id,
        "message": "Задача создана из веб-версии",
    }

    await db.execute(
        text(
            """
            INSERT INTO model_tasks (task_id, user_id, status, result)
            VALUES (:task_id, :user_id, 'PENDING', :result)
            """
        ),
        {
            "task_id": task_id,
            "user_id": user_id,
            "result": json.dumps(initial_result, ensure_ascii=False),
        },
    )
    await db.commit()

    try:
        from app.worker.celery_app import celery_app

        celery_app.send_task(
            "app.worker.tasks.analyze_fashion_photo_task",
            args=[task_id, user_id, photo_id, mode, model_type, "web"],
        )
    except Exception as exc:
        await db.execute(
            text(
                """
                UPDATE model_tasks
                SET status = 'FAILURE',
                    result = :result,
                    updated_at = CURRENT_TIMESTAMP
                WHERE task_id = :task_id
                """
            ),
            {
                "task_id": task_id,
                "result": json.dumps(
                    {
                        "ok": False,
                        "source": "web",
                        "mode": mode,
                        "model_type": model_type,
                        "photo_id": photo_id,
                        "error": "QUEUE_ERROR",
                        "message": str(exc),
                        "text": "😔 Не удалось поставить задачу в очередь. Проверьте Redis/Celery worker.",
                    },
                    ensure_ascii=False,
                ),
            },
        )
        await db.commit()
        raise HTTPException(status_code=500, detail="Не удалось поставить задачу в очередь") from exc

    return {
        "task_id": task_id,
        "status": "PENDING",
        "mode": mode,
        "model_type": model_type,
        "photo_id": photo_id,
    }


@router.get("/tasks/{task_id}")
async def get_fashion_task(
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    result = await db.execute(
        text(
            """
            SELECT task_id, status, result, created_at, updated_at
            FROM model_tasks
            WHERE task_id = :task_id
              AND user_id = :user_id
            LIMIT 1
            """
        ),
        {"task_id": task_id, "user_id": str(current_user.id)},
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    return {
        "task_id": row["task_id"],
        "status": row["status"],
        "result": _safe_json_loads(row["result"]),
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
    }


@router.get("/history")
async def get_fashion_history(
    mode: str | None = Query(default=None, pattern="^(recommendation|outfit|rec)$"),
    limit: int = Query(default=30, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    normalized_mode = _normalize_mode(mode) if mode else None

    if normalized_mode:
        result = await db.execute(
            text(
                """
                SELECT task_id, status, result, created_at, updated_at
                FROM model_tasks
                WHERE user_id = :user_id
                  AND result IS NOT NULL
                  AND COALESCE(result::jsonb ->> 'mode', '') = :mode
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"user_id": str(current_user.id), "mode": normalized_mode, "limit": limit},
        )
    else:
        result = await db.execute(
            text(
                """
                SELECT task_id, status, result, created_at, updated_at
                FROM model_tasks
                WHERE user_id = :user_id
                  AND result IS NOT NULL
                  AND COALESCE(result::jsonb ->> 'mode', '') IN ('recommendation', 'outfit')
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"user_id": str(current_user.id), "limit": limit},
        )

    items: list[dict[str, Any]] = []
    for row in result.mappings().all():
        payload = _safe_json_loads(row["result"]) or {}
        items.append(
            {
                "task_id": row["task_id"],
                "status": row["status"],
                "result": payload,
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
            }
        )

    return {"items": items}

@router.get("/stats")
async def get_fashion_stats(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, int]:
    """Счётчики для панели управления: только успешно готовые рекомендации и образы."""
    result = await db.execute(
        text(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE status = 'SUCCESS'
                      AND COALESCE(result::jsonb ->> 'mode', '') = 'recommendation'
                      AND COALESCE(result::jsonb ->> 'ok', 'false') = 'true'
                ) AS recommendations,
                COUNT(*) FILTER (
                    WHERE status = 'SUCCESS'
                      AND COALESCE(result::jsonb ->> 'mode', '') = 'outfit'
                      AND COALESCE(result::jsonb ->> 'ok', 'false') = 'true'
                ) AS outfits
            FROM model_tasks
            WHERE user_id = :user_id
              AND result IS NOT NULL
              AND COALESCE(result::jsonb ->> 'mode', '') IN ('recommendation', 'outfit')
            """
        ),
        {"user_id": str(current_user.id)},
    )
    row = result.mappings().first() or {}
    return {
        "recommendations": int(row.get("recommendations") or 0),
        "outfits": int(row.get("outfits") or 0),
    }

