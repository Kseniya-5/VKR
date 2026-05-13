import os
import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from app.worker.celery_app import celery_app


DATABASE_URL = "postgresql+asyncpg://fashion_user:fashion_pass@db:5432/fashion_db"


def get_database_url() -> str:
    return (
        os.getenv("DATABASE_URL")
        or DATABASE_URL
    )


async def _create_session_factory():
    engine = create_async_engine(
        get_database_url(),
        future=True,
        pool_pre_ping=True,
    )
    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
    )
    return engine, session_factory


async def _set_task_processing(task_id: str) -> None:
    engine, session_factory = await _create_session_factory()
    try:
        async with session_factory() as session:
            await session.execute(
                text(
                    """
                    UPDATE model_tasks
                    SET status = :status
                    WHERE task_id = :task_id
                    """
                ),
                {
                    "status": "PROCESSING",
                    "task_id": task_id,
                },
            )
            await session.commit()
    finally:
        await engine.dispose()


async def _set_task_success(task_id: str, result_text: str) -> None:
    engine, session_factory = await _create_session_factory()
    try:
        async with session_factory() as session:
            await session.execute(
                text(
                    """
                    UPDATE model_tasks
                    SET status = :status,
                        result = :result
                    WHERE task_id = :task_id
                    """
                ),
                {
                    "status": "SUCCESS",
                    "result": result_text,
                    "task_id": task_id,
                },
            )
            await session.commit()
    finally:
        await engine.dispose()


async def _set_task_failed(task_id: str, error_text: str) -> None:
    engine, session_factory = await _create_session_factory()
    try:
        async with session_factory() as session:
            await session.execute(
                text(
                    """
                    UPDATE model_tasks
                    SET status = :status,
                        result = :result
                    WHERE task_id = :task_id
                    """
                ),
                {
                    "status": "FAILED",
                    "result": error_text,
                    "task_id": task_id,
                },
            )
            await session.commit()
    finally:
        await engine.dispose()


async def _train_model_async(task_id: str, model_params) -> str:
    await _set_task_processing(task_id)

    await asyncio.sleep(10)

    result_text = f"Модель успешно обучена с параметрами: {model_params}"

    await _set_task_success(task_id, result_text)
    return result_text


async def _cleanup_user_data_async(user_id: str) -> dict:
    engine, session_factory = await _create_session_factory()
    try:
        async with session_factory() as session:
            await session.execute(
                text(
                    """
                    UPDATE users
                    SET is_deleted = TRUE,
                        deleted_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = :user_id
                    """
                ),
                {"user_id": user_id},
            )

            await session.execute(
                text(
                    """
                    DELETE FROM account_link_codes
                    WHERE user_id = :user_id
                    """
                ),
                {"user_id": user_id},
            )

            await session.execute(
                text(
                    """
                    DELETE FROM telegram_accounts
                    WHERE user_id = :user_id
                    """
                ),
                {"user_id": user_id},
            )

            await session.execute(
                text(
                    """
                    DELETE FROM web_accounts
                    WHERE user_id = :user_id
                    """
                ),
                {"user_id": user_id},
            )

            await session.execute(
                text(
                    """
                    DELETE FROM model_tasks
                    WHERE user_id = :user_id
                    """
                ),
                {"user_id": user_id},
            )

            await session.commit()

        return {
            "status": "SUCCESS",
            "message": f"Пользователь {user_id} и связанные данные очищены",
        }
    except Exception as e:
        return {
            "status": "FAILED",
            "message": str(e),
        }
    finally:
        await engine.dispose()


@celery_app.task(bind=True, name="train_model_task")
def train_model_task(self, task_id: str, model_params):
    try:
        return asyncio.run(_train_model_async(task_id, model_params))
    except Exception as e:
        try:
            asyncio.run(_set_task_failed(task_id, str(e)))
        except Exception:
            pass
        return str(e)


@celery_app.task(bind=True, name="cleanup_user_data_task")
def cleanup_user_data_task(self, user_id: str):
    return asyncio.run(_cleanup_user_data_async(user_id))