from celery import Celery
import time

app = Celery('fashion_tasks', broker='redis://redis:6379/0', backend='redis://redis:6379/1')


@app.task(bind=True)
def train_model_task(self, model_params):
    # Имитация долгой работы тк нет еще обучающей модели
    time.sleep(10)

    return "Модель успешно обучена"
