from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from uuid import UUID
from sqlalchemy import delete, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models import User, TelegramAccount, WebAccount, ModelTask
from app.worker.tasks import cleanup_user_data_task


class UserDeletionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def _get_user(self, user_id: UUID | str) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _commit_or_rollback(self) -> None:
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise

    async def user_exists(self, user_id: UUID | str) -> bool:
        user = await self._get_user(user_id)
        return user is not None

    async def get_user_status(self, user_id: UUID | str) -> dict[str, Any]:
        user = await self._get_user(user_id)
        if not user:
            return {
                "exists": False,
                "is_deleted": None,
                "deleted_at": None,
            }

        return {
            "exists": True,
            "is_deleted": bool(user.is_deleted),
            "deleted_at": user.deleted_at,
        }

    async def has_telegram_account(self, user_id: UUID | str) -> bool:
        stmt = select(TelegramAccount.telegram_id).where(TelegramAccount.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def has_web_account(self, user_id: UUID | str) -> bool:
        stmt = select(WebAccount.id).where(WebAccount.user_id == user_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def unlink_telegram(self, user_id: UUID | str) -> dict[str, Any]:
        user = await self._get_user(user_id)
        if not user:
            return {
                "success": False,
                "action": "unlink_telegram",
                "reason": "user_not_found",
                "deleted_count": 0,
            }

        stmt = delete(TelegramAccount).where(TelegramAccount.user_id == user_id)

        try:
            result = await self.db.execute(stmt)
            await self._commit_or_rollback()

            return {
                "success": True,
                "action": "unlink_telegram",
                "deleted_count": result.rowcount or 0,
            }
        except SQLAlchemyError as e:
            await self.db.rollback()
            return {
                "success": False,
                "action": "unlink_telegram",
                "reason": "database_error",
                "error": str(e),
                "deleted_count": 0,
            }

    async def delete_web_account(self, user_id: UUID | str) -> dict[str, Any]:
        user = await self._get_user(user_id)
        if not user:
            return {
                "success": False,
                "action": "delete_web_account",
                "reason": "user_not_found",
                "deleted_count": 0,
            }

        stmt = delete(WebAccount).where(WebAccount.user_id == user_id)

        try:
            result = await self.db.execute(stmt)
            await self._commit_or_rollback()

            return {
                "success": True,
                "action": "delete_web_account",
                "deleted_count": result.rowcount or 0,
            }
        except SQLAlchemyError as e:
            await self.db.rollback()
            return {
                "success": False,
                "action": "delete_web_account",
                "reason": "database_error",
                "error": str(e),
                "deleted_count": 0,
            }

    async def soft_delete_user(self, user_id: UUID | str) -> dict[str, Any]:
        user = await self._get_user(user_id)
        if not user:
            return {
                "success": False,
                "action": "soft_delete_user",
                "reason": "user_not_found",
            }

        if user.is_deleted:
            return {
                "success": True,
                "action": "soft_delete_user",
                "already_deleted": True,
                "deleted_at": user.deleted_at,
            }

        now = datetime.now(timezone.utc)

        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(
                is_deleted=True,
                deleted_at=now,
                updated_at=now,
            )
        )

        try:
            result = await self.db.execute(stmt)
            await self._commit_or_rollback()

            return {
                "success": True,
                "action": "soft_delete_user",
                "updated_count": result.rowcount or 0,
                "deleted_at": now,
            }
        except SQLAlchemyError as e:
            await self.db.rollback()
            return {
                "success": False,
                "action": "soft_delete_user",
                "reason": "database_error",
                "error": str(e),
            }

    async def anonymize_or_delete_tasks(self, user_id: UUID | str) -> dict[str, Any]:
        user = await self._get_user(user_id)
        if not user:
            return {
                "success": False,
                "action": "delete_tasks",
                "reason": "user_not_found",
                "deleted_count": 0,
            }

        stmt = delete(ModelTask).where(ModelTask.user_id == user_id)

        try:
            result = await self.db.execute(stmt)
            await self._commit_or_rollback()

            return {
                "success": True,
                "action": "delete_tasks",
                "deleted_count": result.rowcount or 0,
            }
        except SQLAlchemyError as e:
            await self.db.rollback()
            return {
                "success": False,
                "action": "delete_tasks",
                "reason": "database_error",
                "error": str(e),
                "deleted_count": 0,
            }

    async def delete_account_data(self, user_id: UUID | str) -> dict[str, Any]:
        user = await self._get_user(user_id)
        if not user:
            return {
                "success": False,
                "action": "delete_account_data",
                "reason": "user_not_found",
            }

        summary: dict[str, Any] = {
            "success": False,
            "action": "delete_account_data",
            "user_id": str(user_id),
            "steps": {},
        }

        try:
            now = datetime.now(timezone.utc)

            soft_delete_stmt = (
                update(User)
                .where(User.id == user_id)
                .values(
                    is_deleted=True,
                    deleted_at=now,
                    updated_at=now,
                )
            )
            soft_delete_result = await self.db.execute(soft_delete_stmt)
            summary["steps"]["soft_delete_user"] = {
                "updated_count": soft_delete_result.rowcount or 0,
                "deleted_at": now.isoformat(),
            }

            unlink_tg_stmt = delete(TelegramAccount).where(TelegramAccount.user_id == user_id)
            unlink_tg_result = await self.db.execute(unlink_tg_stmt)
            summary["steps"]["unlink_telegram"] = {
                "deleted_count": unlink_tg_result.rowcount or 0,
            }

            delete_web_stmt = delete(WebAccount).where(WebAccount.user_id == user_id)
            delete_web_result = await self.db.execute(delete_web_stmt)
            summary["steps"]["delete_web_account"] = {
                "deleted_count": delete_web_result.rowcount or 0,
            }

            delete_tasks_stmt = delete(ModelTask).where(ModelTask.user_id == user_id)
            delete_tasks_result = await self.db.execute(delete_tasks_stmt)
            summary["steps"]["delete_tasks"] = {
                "deleted_count": delete_tasks_result.rowcount or 0,
            }

            await self._commit_or_rollback()

            summary["success"] = True
            return summary

        except SQLAlchemyError as e:
            await self.db.rollback()
            summary["reason"] = "database_error"
            summary["error"] = str(e)
            return summary

    async def restore_user(self, user_id: UUID | str) -> dict[str, Any]:
        user = await self._get_user(user_id)
        if not user:
            return {
                "success": False,
                "action": "restore_user",
                "reason": "user_not_found",
            }

        if not user.is_deleted:
            return {
                "success": True,
                "action": "restore_user",
                "already_restored": True,
            }

        now = datetime.now(timezone.utc)

        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(
                is_deleted=False,
                deleted_at=None,
                updated_at=now,
            )
        )

        try:
            result = await self.db.execute(stmt)
            await self._commit_or_rollback()

            return {
                "success": True,
                "action": "restore_user",
                "updated_count": result.rowcount or 0,
            }
        except SQLAlchemyError as e:
            await self.db.rollback()
            return {
                "success": False,
                "action": "restore_user",
                "reason": "database_error",
                "error": str(e),
            }


def enqueue_cleanup_user_data(user_id: str):
    
    return cleanup_user_data_task.delay(user_id)