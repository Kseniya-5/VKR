import os
import time
import psycopg2
from psycopg2.extras import RealDictCursor

from app.worker.celery_app import celery_app


def get_db_connection():
    return psycopg2.connect(
        os.getenv("DATABASE_URL"),
        cursor_factory=RealDictCursor,
    )


@celery_app.task(bind=True, name="train_model_task")
def train_model_task(self, task_id: str, model_params):
    conn = None
    cursor = None

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE model_tasks SET status = %s WHERE task_id = %s",
            ("PROCESSING", task_id),
        )
        conn.commit()

        # здесь будет реальное обучение
        time.sleep(10)

        result_text = f"Модель успешно обучена с параметрами: {model_params}"

        cursor.execute(
            "UPDATE model_tasks SET status = %s, result = %s WHERE task_id = %s",
            ("SUCCESS", result_text, task_id),
        )
        conn.commit()

        return result_text

    except Exception as e:
        if conn is not None:
            try:
                cursor.execute(
                    "UPDATE model_tasks SET status = %s, result = %s WHERE task_id = %s",
                    ("FAILED", str(e), task_id),
                )
                conn.commit()
            except Exception:
                pass
        return str(e)

    finally:
        if cursor is not None:
            cursor.close()
        if conn is not None:
            conn.close()