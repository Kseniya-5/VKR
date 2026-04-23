import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

BROKER_URL = REDIS_URL
BACKEND_URL = (
    REDIS_URL.replace("/0", "/1") if REDIS_URL.endswith("/0") else "redis://redis:6379/1"
)

celery_app = Celery(
    "fashion_tasks",
    broker=BROKER_URL,
    backend=BACKEND_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
)

celery_app.autodiscover_tasks(packages=["app.worker"])