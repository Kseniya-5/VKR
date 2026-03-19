#!/bin/sh

if [ -z "$BOT_TOKEN" ]; then
    echo "Ошибка: BOT_TOKEN не установлен! Пожалуйста, добавьте его в файл .env"
    exit 1
fi

exec python bot.py
