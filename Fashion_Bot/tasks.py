from celery import Celery
import time
import psycopg2
import os

broker_url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
backend_url = broker_url.replace('/0', '/1') if broker_url.endswith('/0') else 'redis://redis:6379/1'
app = Celery('fashion_tasks', broker=broker_url, backend=backend_url)


def get_db_connection():
    return psycopg2.connect(os.getenv('DATABASE_URL'))


@app.task(bind=True)
def train_model_task(self, task_id, model_params):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("UPDATE model_tasks SET status = %s WHERE task_id = %s", ('PROCESSING', task_id))
        conn.commit()

        # Имитация долгой работы (обучение)
        time.sleep(10)

        result_text = f"Модель успешно обучена с параметрами: {model_params}"
        cursor.execute("UPDATE model_tasks SET status = %s, result = %s WHERE task_id = %s",
                       ('SUCCESS', result_text, task_id))
        conn.commit()

        return result_text
    except Exception as e:
        cursor.execute("UPDATE model_tasks SET status = %s, result = %s WHERE task_id = %s",
                       ('FAILED', str(e), task_id))
        conn.commit()
        return str(e)
    finally:
        cursor.close()
        conn.connect().close()
