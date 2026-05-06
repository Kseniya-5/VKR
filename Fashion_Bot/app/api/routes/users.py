from __future__ import annotations

from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.users import (
    DeleteAccountRequest,
    MessageResponse,
    UserProfileResponse,
)
from app.core.deps import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.services.user_deletion import UserDeletionService
from app.worker.tasks import train_model_task


router = APIRouter(prefix="/users", tags=["users"])


class TrainModelRequest(BaseModel):
    user_id: str
    model_params: dict

class UpdateProfileRequest(BaseModel):
    first_name: str | None = Field(None, max_length=255)
    last_name: str | None = Field(None, max_length=255)


class TelegramInfoResponse(BaseModel):
    telegram_id: int | None
    username: str | None
    first_name: str | None
    last_name: str | None


class WebAccountInfoResponse(BaseModel):
    email: str | None

def _validate_delete_confirmation(confirm_text: str) -> None:
    if confirm_text.strip().upper() != "DELETE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Invalid confirmation text. Please send "DELETE".',
        )


def _ensure_user_exists(user_status: dict) -> None:
    if not user_status.get("exists"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )


def _ensure_user_not_deleted(user_status: dict) -> None:
    _ensure_user_exists(user_status)
    if user_status.get("is_deleted"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is deleted. Restore the account before performing this action.",
        )


@router.get(
    "/me",
    response_model=UserProfileResponse,
    summary="Получить профиль текущего пользователя",
    responses={
        401: {"description": "Unauthorized"},
        404: {"description": "User not found"},
    },
)
async def get_me(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserProfileResponse:
    service = UserDeletionService(db)

    user_status = await service.get_user_status(current_user.id)
    _ensure_user_exists(user_status)

    has_telegram = await service.has_telegram_account(current_user.id)
    has_web_account = await service.has_web_account(current_user.id)

    return UserProfileResponse(
        id=str(current_user.id),
        is_deleted=bool(user_status["is_deleted"]),
        has_telegram=has_telegram,
        has_web_account=has_web_account,
    )

@router.patch(
    "/me",
    response_model=MessageResponse,
    summary="Обновить профиль пользователя",
)
async def update_me(
    payload: UpdateProfileRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    """
    Обновляет имя/фамилию в telegram_accounts 
    """
    service = UserDeletionService(db)
    user_status = await service.get_user_status(current_user.id)
    _ensure_user_not_deleted(user_status)

    has_telegram = await service.has_telegram_account(current_user.id)
    if not has_telegram:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Telegram account linked. Profile update is only available for Telegram users.",
        )

    updates = {}
    if payload.first_name is not None:
        updates["first_name"] = payload.first_name
    if payload.last_name is not None:
        updates["last_name"] = payload.last_name

    if not updates:
        return MessageResponse(message="No changes provided")

    set_clause = ", ".join([f"{k} = :{k}" for k in updates.keys()])
    
    await db.execute(
        text(
            f"""
            UPDATE telegram_accounts
            SET {set_clause}
            WHERE user_id = :user_id
            """
        ),
        {**updates, "user_id": str(current_user.id)},
    )
    await db.commit()

    return MessageResponse(message="Profile updated successfully")


@router.get(
    "/me/telegram",
    response_model=TelegramInfoResponse,
    summary="Получить информацию о привязанном Telegram",
)
async def get_my_telegram_info(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TelegramInfoResponse:
    result = await db.execute(
        text(
            """
            SELECT telegram_id, username, first_name, last_name
            FROM telegram_accounts
            WHERE user_id = :user_id
            LIMIT 1
            """
        ),
        {"user_id": str(current_user.id)},
    )
    row = result.mappings().first()

    if not row:
        return TelegramInfoResponse(
            telegram_id=None,
            username=None,
            first_name=None,
            last_name=None,
        )

    return TelegramInfoResponse(
        telegram_id=row["telegram_id"],
        username=row["username"],
        first_name=row["first_name"],
        last_name=row["last_name"],
    )


@router.get(
    "/me/web-account",
    response_model=WebAccountInfoResponse,
    summary="Получить информацию о веб-аккаунте",
)
async def get_my_web_account_info(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WebAccountInfoResponse:
    result = await db.execute(
        text(
            """
            SELECT email
            FROM web_accounts
            WHERE user_id = :user_id
            LIMIT 1
            """
        ),
        {"user_id": str(current_user.id)},
    )
    row = result.mappings().first()

    if not row:
        return WebAccountInfoResponse(email=None)

    return WebAccountInfoResponse(email=row["email"])

@router.delete(
    "/me/telegram-link",
    response_model=MessageResponse,
    summary="Отвязать Telegram от текущего пользователя",
    responses={
        401: {"description": "Unauthorized"},
        404: {"description": "User not found"},
        409: {"description": "User is deleted"},
    },
)
async def unlink_my_telegram(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    service = UserDeletionService(db)

    user_status = await service.get_user_status(current_user.id)
    _ensure_user_not_deleted(user_status)

    result = await service.unlink_telegram(current_user.id)

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error") or "Failed to unlink Telegram account",
        )

    deleted_count = result.get("deleted_count", 0)

    if deleted_count == 0:
        return MessageResponse(message="Telegram account is already unlinked")

    return MessageResponse(message="Telegram account unlinked successfully")


@router.delete(
    "/me/web-account",
    response_model=MessageResponse,
    summary="Удалить web-аккаунт текущего пользователя",
    responses={
        401: {"description": "Unauthorized"},
        404: {"description": "User not found"},
        409: {"description": "User is deleted"},
    },
)
async def delete_my_web_account(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    service = UserDeletionService(db)

    user_status = await service.get_user_status(current_user.id)
    _ensure_user_not_deleted(user_status)

    result = await service.delete_web_account(current_user.id)

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error") or "Failed to delete web account",
        )

    deleted_count = result.get("deleted_count", 0)

    if deleted_count == 0:
        return MessageResponse(message="Web account is already deleted")

    return MessageResponse(message="Web account deleted successfully")


@router.delete(
    "/me",
    response_model=MessageResponse,
    summary="Удалить текущего пользователя и связанные данные",
    responses={
        400: {"description": "Invalid confirmation text"},
        401: {"description": "Unauthorized"},
        404: {"description": "User not found"},
    },
)
async def delete_me(
    payload: DeleteAccountRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    _validate_delete_confirmation(payload.confirm_text)

    service = UserDeletionService(db)

    user_status = await service.get_user_status(current_user.id)
    _ensure_user_exists(user_status)

    if user_status.get("is_deleted"):
        return MessageResponse(message="Account is already deleted")

    result = await service.delete_account_data(current_user.id)

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error") or "Failed to delete account",
        )

    return MessageResponse(message="Account and related data deleted successfully")


@router.post(
    "/me/restore",
    response_model=MessageResponse,
    summary="Восстановить мягко удаленного пользователя",
    responses={
        401: {"description": "Unauthorized"},
        404: {"description": "User not found"},
    },
)
async def restore_me(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    service = UserDeletionService(db)

    user_status = await service.get_user_status(current_user.id)
    _ensure_user_exists(user_status)

    result = await service.restore_user(current_user.id)

    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.get("error") or "Failed to restore user",
        )

    if result.get("already_restored"):
        return MessageResponse(message="User is already active")

    return MessageResponse(message="User restored successfully")


@router.post(
    "/train-model",
    summary="Поставить обучение модели в очередь Celery",
)
async def start_train_model(
    payload: TrainModelRequest,
    db: AsyncSession = Depends(get_db),
):
    user_result = await db.execute(
        text(
            """
            SELECT id
            FROM users
            WHERE id = :user_id
            LIMIT 1
            """
        ),
        {"user_id": payload.user_id},
    )
    user_exists = user_result.scalar_one_or_none()

    if user_exists is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    task_id = str(uuid4())

    await db.execute(
        text(
            """
            INSERT INTO model_tasks (
                task_id,
                user_id,
                status,
                result
            )
            VALUES (
                :task_id,
                :user_id,
                :status,
                :result
            )
            """
        ),
        {
            "task_id": task_id,
            "user_id": payload.user_id,
            "status": "PENDING",
            "result": None,
        },
    )
    await db.commit()

    train_model_task.delay(task_id, payload.model_params)

    return {
        "message": "Задача обучения поставлена в очередь",
        "task_id": task_id,
        "status": "PENDING",
    }


@router.get(
    "/tasks/{task_id}",
    summary="Получить статус задачи обучения",
)
async def get_model_task_status(
    task_id: str,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        text(
            """
            SELECT
                task_id,
                user_id,
                status,
                result,
                created_at,
                updated_at
            FROM model_tasks
            WHERE task_id = :task_id
            LIMIT 1
            """
        ),
        {"task_id": task_id},
    )
    row = result.mappings().first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Task not found",
        )

    return dict(row)