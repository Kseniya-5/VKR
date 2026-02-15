# Fashion Bot Project

## Обзор
Этот репозиторий содержит реализацию проекта Fashion Bot в рамках курсовой работы. Проект настроен для запуска в изолированной Docker-среде, что обеспечивает согласованное выполнение на различных системах.


## Требования
- Docker 20.10+
- Docker Compose v2+
- Аккаунт Telegram и созданный бот через [BotFather][web:13]

> Вам нужен токен бота `BOT_TOKEN`, который выдаёт BotFather.[web:13]

## Структура проекта
> `Fashion_Bot/`  
> &nbsp;&nbsp;├── `.gitignore` — Игнорируемые файлы \
> &nbsp;&nbsp;├── `Dockerfile` — Конфигурация Docker-образа для контейнеризации приложения \
> &nbsp;&nbsp;├── `README.md` — Документация проекта \
> &nbsp;&nbsp;├── `bot.py` — Точка входа бота: инициализация диспетчера, запуск поллинга/вебхуков\
> &nbsp;&nbsp;├── `config.py` —  Настройки приложения: токен бота, параметры подключения к БД, конфигурация логгера\
> &nbsp;&nbsp;├── `docker-compose.yml` —  Файл с описанием сервисов (бот и Redis)\
> &nbsp;&nbsp;├── `handlers.py` —  Обработчики команд и сообщений пользователя\
> &nbsp;&nbsp;├── `middlewares.py` —  Промежуточное ПО: троттлинг, логирование запросов, обработка ошибок\
> &nbsp;&nbsp;├── `pyproject.toml` —  Управление зависимостями и метаданными проекта (Poetry)\
> &nbsp;&nbsp;└── `uv.lock` —  Фиксированные версии зависимостей (uv package manager)



## Настройка и запуск
1. Склонируйте репозиторий:
   ```bash
   git clone https://github.com/Kseniya-5/VKR.git
   cd VKR/Fashion_Bot
   ```

2. Соберите Docker-образ:
   ```bash
   docker build -t fashion-bot .
   ```

3. Запустите контейнер:
   ```bash
   docker run -d -p 8000:8000 fashion-bot
   ```

4. Создайте файл `.env` в корне проекта:
   ```env
   BOT_TOKEN=ваш_токен_из_BotFather
   ```

   
