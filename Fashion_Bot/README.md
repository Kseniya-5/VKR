# Fashion Bot Project

### Автор: Балицкая Ксения

## Обзор
Этот репозиторий содержит реализацию проекта Fashion Bot в рамках курсовой работы. Проект настроен для запуска в изолированной Docker-среде, что обеспечивает согласованное выполнение на различных системах.

## Требования
- Docker 20.10+
- Docker Compose v2+
- Аккаунт Telegram и созданный бот через BotFather
- Обеспечить сетевой доступ к Telegram


## Подготовка окружения (Важно!)
Перед запуском любым из способов необходимо создать файл с переменными окружения:
1. Создайте файл `.env` в корне проекта (`VKR/Fashion_Bot/.env`).
2. Скопируйте в него следующие настройки и замените значение `BOT_TOKEN` на ваш токен от @BotFather:
   ```env
   # Токен вашего Telegram-бота (ОБЯЗАТЕЛЬНО ЗАМЕНИТЬ НА СВОЙ)
   BOT_TOKEN=ваш_токен_из_BotFather
   
   # Оставить по умолчанию для работы внутри кластера
   REDIS_URL=redis://redis:6379/0
   
   # Учетные данные для базы данных PostgreSQL (задайте свои значения)
   POSTGRES_USER=ваш_пользователь_БД
   POSTGRES_PASSWORD=ваш_пароль_БД
   POSTGRES_DB=название_вашей_БД
   
   # Строка подключения для Python-приложения (должна совпадать с данными выше)
   DATABASE_URL=postgresql://ваш_пользователь_БД:ваш_пароль_БД@db:5432/название_вашей_БД
   
   # Ваш логин на GitHub (в нижнем регистре)
   GHCR_USERNAME=your_login
   # Personal Access Token (classic) с правами write:packages, read:packages, delete:packages
   GHCR_TOKEN=ghp_***
   ```

#### Как получить токен бота?
1. Свяжитесь с @BotFather
2. Выполните команду /newbot и следуйте инструкциям, пока вам не будет выдан новый токен

## Структура проекта
> `Fashion_Bot/` \
> &nbsp;&nbsp;│── `k8s/` — Папка с манифестами для развертывания в Kubernetes \
> &nbsp;&nbsp;│&nbsp;&nbsp; ├── `bot.yaml` — Deployment и Service для Telegram-бота \
> &nbsp;&nbsp;│&nbsp;&nbsp; ├── `configmap.yaml` — Открытые переменные окружения для кластера \
> &nbsp;&nbsp;│&nbsp;&nbsp; ├── `bd-init-configmap.yaml` — ConfigMap со скриптом инициализации БД \
> &nbsp;&nbsp;│&nbsp;&nbsp; ├── `migration-job.yaml` — Job для одноразового запуска SQL-миграций до старта приложения \
> &nbsp;&nbsp;│&nbsp;&nbsp; ├── `nginx.yaml` — Deployment и NodePort Service для Nginx \
> &nbsp;&nbsp;│&nbsp;&nbsp; ├── `postgres.yaml` — Deployment и Service для базы данных PostgreSQL \
> &nbsp;&nbsp;│&nbsp;&nbsp; ├── `redis.yaml` — Deployment и Service для брокера сообщений \
> &nbsp;&nbsp;│ &nbsp;&nbsp;└── `worker.yaml` — Deployment для фоновых задач Celery \
> &nbsp;&nbsp;│── `nginx/` — Папка с конфигурацией Nginx сервера \
> &nbsp;&nbsp;│&nbsp;&nbsp; ├── `Dockerfile` — Сборка образа Nginx \
> &nbsp;&nbsp;│ &nbsp;&nbsp;└── `nginx.conf` — Настройки Reverse proxy и отдачи статики \
>  &nbsp;&nbsp;├── `.dockerignore` — Файлы и папки, исключаемые из контекста сборки Docker-образа  \
> &nbsp;&nbsp;├── `.gitignore` — Игнорируемые файлы \
> &nbsp;&nbsp;├── `Dockerfile` — Конфигурация Docker-образа для контейнеризации приложения \
> &nbsp;&nbsp;├── `README.md` — Документация проекта \
> &nbsp;&nbsp;├── `bot.py` — Точка входа бота: инициализация диспетчера, запуск поллинга/вебхуков\
> &nbsp;&nbsp;├── `config.py` —  Настройки приложения: токен бота, параметры подключения к БД, конфигурация логгера\
> &nbsp;&nbsp;├── `deploy.sh` —  Bash-скрипт для автоматической сборки образов, генерации секретов и деплоя в k8s !!! \
> &nbsp;&nbsp;├── `docker-compose.yml` —  Файл с описанием сервисов (бот и Redis)\
> &nbsp;&nbsp;├── `entrypoint.sh` —  Скрипт проверки переменных и запуска бота\
> &nbsp;&nbsp;├── `handlers.py` —  Обработчики команд и сообщений пользователя\
> &nbsp;&nbsp;├── `init.sql` —  Скрипт создания таблиц в базе данных при первом запуске\
> &nbsp;&nbsp;├── `middlewares.py` —  Промежуточное ПО: троттлинг, логирование запросов, обработка ошибок\
> &nbsp;&nbsp;├── `pyproject.toml` —  Управление зависимостями и метаданными проекта (Poetry)\
> &nbsp;&nbsp;├── `stop.sh` —  Bash-скрипт для быстрой очистки кластера от подов, сервисов и секретов проекта !!! \
> &nbsp;&nbsp;├── `task.py` —  Celery-воркер: логика долгих задач и обновление статусов в БД\
> &nbsp;&nbsp;├── `uv.lock` —  Фиксированные версии зависимостей (uv package manager)\
> &nbsp;&nbsp;└── `web_app.py` —  Простой aiohttp веб-сервер для связи с Nginx (Production mode)

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

***

### 2. Локально проверить работу ТГ + Веб 
```bash
# 1. Почистить всё лишнее и пересобрать заново
docker builder prune -a -f
docker system prune -a --volumes -f

# 2. Создай уникальные теги образов
export TAG=$(date +%Y%m%d%H%M%S)

export BOT_IMAGE=fashion-bot:$TAG
export NGINX_IMAGE=fashion-nginx:$TAG

echo $BOT_IMAGE
echo $NGINX_IMAGE

# 3. Собери backend/bot/worker образ
docker build --no-cache -t $BOT_IMAGE .
minikube image load $BOT_IMAGE

# 4. Собери Nginx/frontend образ
docker build --no-cache -t $NGINX_IMAGE ./nginx
minikube image load $NGINX_IMAGE

# 5. Временно подставь новые image tags в Kubernetes
kubectl get deploy

kubectl set image deployment/fashion-api fashion-api=$BOT_IMAGE
kubectl set image deployment/telegram-bot telegram-bot=$BOT_IMAGE
kubectl set image deployment/worker worker=$BOT_IMAGE
kubectl set image deployment/nginx nginx=$NGINX_IMAGE

# 6. Принудительно перезапусти deployment’ы
kubectl rollout restart deployment/fashion-api
kubectl rollout restart deployment/telegram-bot
kubectl rollout restart deployment/worker
kubectl rollout restart deployment/nginx

# 7. Проверка маршрутов через port-forward
kubectl port-forward svc/nginx-service 8080:80

# 8. Смотрим
curl -i http://localhost:8080/

```

***

### 3. Очистить всю тестовую БД перед внедрением
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





   
