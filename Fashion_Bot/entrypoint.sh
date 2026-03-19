#!/bin/sh

set -e

if [ -z "$DATABASE_URL" ]; then
    echo "Ошибка: DATABASE_URL не установлен!"
    exit 1
fi

if [ -z "$REDIS_URL" ]; then
    echo "Ошибка: REDIS_URL не установлен!"
    exit 1
fi

if [ "$1" = "celery" ]; then
    echo "Запуск Celery Worker..."
    exec "$@"
else
    if [ -z "$BOT_TOKEN" ]; then
        echo "Ошибка: BOT_TOKEN не установлен! Пожалуйста, добавьте его в файл .env"
        exit 1
    fi

    echo "Запуск Telegram Бота..."
    exec python bot.py
fi
