# Fashion Bot Project

## Обзор
Этот репозиторий содержит реализацию проекта Fashion Bot в рамках курсовой работы. Проект настроен для запуска в изолированной Docker-среде, что обеспечивает согласованное выполнение на различных системах.

## Структура проекта
> `Fashion_Bot/`  
> &nbsp;&nbsp;├── `.gitignore` — Игнорируемые файлы \
> &nbsp;&nbsp;├── `Dockerfile` — Конфигурация Docker-образа для контейнеризации приложения \
> &nbsp;&nbsp;├── `README.md` — Документация проекта \
> &nbsp;&nbsp;├── `bot.py` — Точка входа бота: инициализация диспетчера, запуск поллинга/вебхуков\
> &nbsp;&nbsp;├── `config.py` —  Настройки приложения: токен бота, параметры подключения к БД, конфигурация логгера\
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

2. Соберите Docker-образ для linux:
   ```bash
   sudo docker build -t fashion-bot .
   ```

3. Запустите контейнер:
   ```bash
   sudo docker run -d --env-file .env --name my-fashion-bot fashion-bot
   ```

4. Проверь логи
   ```bash
   sudo docker logs my-fashion-bot
   ```
   
### Если нужно пересобрать Docker-образ

5. Удали старый контейнер
   ```bash
   sudo docker rm my-fashion-bot
   ```

6. Повтори пункты 2-4.
