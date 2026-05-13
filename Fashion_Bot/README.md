# Fashion Bot Project

### Автор: Балицкая Ксения

## Обзор
Этот репозиторий содержит реализацию проекта Fashion Bot в рамках курсовой работы. Проект настроен для запуска в изолированной Docker-среде, что обеспечивает согласованное выполнение на различных системах.

Проект включает:
- Telegram-бота на `aiogram`;
- backend API на `FastAPI`;
- веб-интерфейс на HTML/CSS/JS через `Nginx`;
- PostgreSQL для хранения пользователей, фотографий, задач и истории;
- Redis + Celery для фоновой обработки ML-задач;
- CV-модели для извлечения атрибутов одежды;
- опциональное подключение мультимодальной LLM через Open WebUI/Ollama;
- Kubernetes-манифесты для развёртывания;
- Cloudflare Tunnel для публичного доступа к веб-приложению.

***
## Основные возможности

- Регистрация пользователя через Telegram.
- Регистрация и вход в веб-версии.
- Связь Telegram-аккаунта и веб-аккаунта.
- Одноразовый вход в веб-версию по ссылке из Telegram.
- Восстановление доступа через Telegram.
- Загрузка фотографий через Telegram и веб.
- Автоматическая конвертация изображений в JPEG.
- Общий гардероб между Telegram и web.
- Просмотр и удаление фотографий.
- Получение рекомендаций по одежде.
- Сбор образа.
- История рекомендаций и образов в веб-версии.
- Фоновая обработка ML-задач через Celery worker.
- Защищённый доступ к пользовательским фотографиям.
- Публичный доступ к веб-версии через Cloudflare Tunnel.

***
## Требования

Для запуска проекта потребуется:

- Docker 20.10+
- kubectl
- Minikube
- Python 3.12+
- Telegram-бот, созданный через BotFather
- PostgreSQL и Redis внутри Kubernetes-кластера
- Доступ к Telegram API
- Опционально: Open WebUI + Ollama для LLM/Vision API
- Опционально: Cloudflare-аккаунт и домен для публичного доступа
- Обеспечить сетевой доступ к Telegram и Веб-версии.
***

## Подготовка Telegram-бота

1. Откройте Telegram.
2. Найдите `@BotFather`.
3. Выполните команду:

```text
/newbot
```

4. Укажите имя и username бота.
5. Скопируйте выданный токен.
6. Добавьте токен в файл `.env` в переменную `BOT_TOKEN`.

---

## Подготовка `.env`

Перед запуском необходимо создать файл `.env` в корне проекта:

```text
Fashion_Bot/.env
```

Пример файла:

```env
# ============================================================
# Telegram
# ============================================================

BOT_TOKEN=ваш_токен_из_BotFather

# ============================================================
# PostgreSQL
# ============================================================

POSTGRES_USER=fashion_user
POSTGRES_PASSWORD=fashion_password
POSTGRES_DB=fashion_db

DATABASE_URL=postgresql+asyncpg://fashion_user:fashion_password@db:5432/fashion_db

# ============================================================
# Redis / Celery
# ============================================================

REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/1

# ============================================================
# Security
# ============================================================

JWT_SECRET_KEY=замените_на_длинный_секретный_ключ
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
PASSWORD_PEPPER=замените_на_секретную_строку

# ============================================================
# URLs
# ============================================================

# Публичный адрес веб-приложения.
# Для локального теста можно временно указать адрес NodePort или tunnel.
PUBLIC_BASE_URL=https://app.fashion-bot.win

# Внутренний адрес API внутри Kubernetes.
API_BASE_URL=http://fashion-api-service:8000

# CORS
CORS_ORIGINS=https://app.fashion-bot.win,http://localhost:8000,http://localhost:8080

# ============================================================
# Vision API / Open WebUI / Ollama
# ============================================================

VISION_API_ENABLED=true
VISION_PROVIDER=openwebui

# Пример:
# API_URL=http://192.168.1.14:3000/api/chat/completions
API_URL=ваш_url_Open_WebUI_api_chat_completions

# API key из Open WebUI.
API_KEY=ваш_openwebui_api_key

VISION_MODEL=llama3.2-vision:latest
OPENWEBUI_AUTH_HEADER=Authorization

VISION_API_TIMEOUT_SECONDS=120
VISION_IMAGE_MAX_SIDE=1280
VISION_IMAGE_JPEG_QUALITY=85

# ============================================================
# Cloudflare Tunnel
# ============================================================

# Если используется Cloudflare Tunnel, сюда добавляется token tunnel connector.
TUNNEL_TOKEN=ваш_cloudflare_tunnel_token
```

> Важно: файл `.env` нельзя коммитить в репозиторий. Он должен быть добавлен в `.gitignore`.

***

## Структура проекта

```text
Fashion_Bot/
│
├── app/
│   ├── api/
│   │   ├── main.py                  # FastAPI-приложение
│   │   ├── routes/
│   │   │   ├── auth.py              # Регистрация, вход, токены, связь аккаунтов
│   │   │   ├── fashion.py           # Рекомендации, образы, ML-задачи
│   │   │   ├── photos.py            # Загрузка, просмотр и удаление фото
│   │   │   └── users.py             # Профиль, настройки, удаление аккаунта
│   │   └── schemas/                 # Pydantic-схемы
│   │
│   ├── bot/
│   │   ├── main.py                  # Запуск Telegram-бота
│   │   ├── handlers/
│   │   │   ├── auth.py              # Регистрация и связь аккаунтов
│   │   │   └── base.py              # Основные сценарии бота
│   │   ├── keyboards.py             # Inline-кнопки
│   │   ├── middlewares.py           # Middleware
│   │   └── states.py                # FSM-состояния
│   │
│   ├── core/
│   │   ├── config.py                # Настройки приложения
│   │   ├── deps.py                  # Зависимости FastAPI
│   │   └── security.py              # JWT, пароли, безопасность
│   │
│   ├── db/
│   │   ├── models.py                # SQLAlchemy-модели
│   │   └── session.py               # Подключение к БД
│   │
│   ├── ml/
│   │   ├── fashion_attributes.py    # Извлечение CV-признаков
│   │   ├── recommendation_engine.py # Генерация рекомендаций
│   │   └── vision_advisor.py        # Интеграция с LLM/Vision API
│   │
│   ├── services/
│   │   └── user_deletion.py         # Логика удаления пользователя и данных
│   │
│   └── worker/
│       ├── celery_app.py            # Celery-приложение
│       └── tasks.py                 # Фоновые задачи
│
├── k8s/
│   ├── api.yaml                     # Deployment/Service для FastAPI
│   ├── bot.yaml                     # Deployment для Telegram-бота
│   ├── worker.yaml                  # Deployment для Celery worker
│   ├── nginx.yaml                   # Deployment/Service для Nginx
│   ├── postgres.yaml                # StatefulSet/Service PostgreSQL
│   ├── redis.yaml                   # Deployment/Service Redis
│   ├── media-pvc.yaml               # PersistentVolumeClaim для фото
│   ├── migration-job.yaml           # Job для применения миграции
│   ├── configmap.yaml               # Неконфиденциальные настройки
│   ├── secret.yaml                  # Шаблон Secret
│   └── cloudflared.yaml             # Cloudflare Tunnel connector
│
├── migrations/
│   └── 001_initial.sql              # Единая SQL-миграция БД
│
├── nginx/
│   ├── Dockerfile                   # Dockerfile для frontend/Nginx
│   ├── nginx.conf                   # Reverse proxy и статика
│   ├── index.html                   # Страница входа/регистрации
│   ├── dashboard.html               # Панель управления
│   ├── photos.html                  # Мои фото
│   ├── profile.html                 # Профиль
│   ├── settings.html                # Настройки
│   ├── recommendations.html         # История рекомендаций
│   ├── outfits.html                 # История образов
│   └── assets/                      # CSS/JS/статические ресурсы
│
├── deploy.sh                        # Сборка и деплой проекта в Kubernetes
├── stop.sh                          # Остановка и очистка ресурсов проекта
├── Dockerfile                       # Dockerfile для backend/bot/worker
├── pyproject.toml                   # Зависимости Python-проекта
├── uv.lock                          # Зафиксированные версии зависимостей
└── README.md
```

***

### 1. Запуск проекта через Kubernetes (Полное Production окружение)
Проект полностью адаптирован для работы в Kubernetes-кластере с использованием `Minikube`. Все манифесты находятся в директории `k8s/`

```bash
# 1. Сделайте скрипт исполняемым (это нужно сделать только один раз):
chmod +x deploy.sh
# 2. Для запуска или обновления проекта достаточно просто написать в терминале:
./deploy.sh

# Управление кластером (Остановка)
# 3. Сделайте скрипт исполняемым (один раз)
chmod +x stop.sh
# 4. Теперь для остановки проекта просто запустите:
./stop.sh
```
Скрипт deploy.sh выполняет:

- сборку Docker-образов;
- загрузку образов в Minikube;
- создание/обновление Kubernetes Secret;
- применение ConfigMap;
- применение PVC;
- запуск PostgreSQL и Redis;
- запуск миграции БД;
- запуск API, Telegram-бота, worker и Nginx;
- перезапуск deployment'ов при обновлении образов.

***

### 2. Очистить всю тестовую БД перед внедрением
```bash
# 1. Зайти в PostgreSQL
kubectl exec -it db-0 -- psql -U fashion_user -d fashion_db

# 2. Выполнить очистку всех таблиц (внутри psql)
DO $$
DECLARE
    r RECORD;
BEGIN
    FOR r IN (
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
    )
    LOOP
        EXECUTE 'TRUNCATE TABLE public.' || quote_ident(r.tablename) || ' RESTART IDENTITY CASCADE';
    END LOOP;
END $$;

# 3. Проверка — должно вернуть 0
SELECT COUNT(*) FROM users;

# 4. Выйти из psql
\q
```
***
## Безопасность

В проекте реализованы следующие меры:

- пароли не хранятся в открытом виде;
- используется хеширование паролей;
- доступ к API выполняется через JWT;
- фотографии не отдаются как публичные static-файлы;
- перед выдачей файла проверяется владелец фотографии;
- пользователь не может получить чужое фото по `photo_id`;
- конфиденциальные параметры хранятся в Kubernetes Secret;
- пользовательский ввод проходит валидацию;
- удаление фотографий выполняется логически через `is_active = false`;
- удаление аккаунта требует подтверждения.

***

## Текущий статус проекта

Реализовано:

- Telegram-бот;
- веб-интерфейс;
- backend API;
- PostgreSQL-схема;
- загрузка и просмотр фотографий;
- синхронизация Telegram и web;
- рекомендации и сбор образа;
- история результатов;
- фоновая обработка через Celery;
- интеграция с Vision API/Open WebUI;
- Kubernetes-деплой;
- публичный домен через Cloudflare Tunnel.

Планируется:

- интеграция графа онтологии Neo4j в пользовательский сервис;
- улучшение качества рекомендаций;
- учёт антропометрических параметров;
- определение цветотипа;
- 3D-визуализация образов;
- рекомендации товаров со ссылками на магазины;
- онлайн-статистика;
- расширенный мониторинг и автоматизированные тесты.




   
