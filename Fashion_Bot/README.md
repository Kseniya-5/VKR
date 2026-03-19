# Fashion Bot Project

## Обзор
Этот репозиторий содержит реализацию проекта Fashion Bot в рамках курсовой работы. Проект настроен для запуска в изолированной Docker-среде, что обеспечивает согласованное выполнение на различных системах.

## Требования
- Docker 20.10+
- Docker Compose v2+
- Аккаунт Telegram и созданный бот через [BotFather][web:13]

> Вам нужен токен бота `BOT_TOKEN`, который выдаёт BotFather.[web:13]

## Подготовка окружения (Важно!)
Перед запуском любым из способов необходимо создать файл с переменными окружения:
1. Создайте файл `.env` в корне проекта (`VKR/Fashion_Bot/.env`).
2. Вставьте в него токен вашего бота:
   ```env
   BOT_TOKEN=ваш_токен_из_BotFather
   ```

## Структура проекта
> `Fashion_Bot/`  
> &nbsp;&nbsp;├── `.gitignore` — Игнорируемые файлы \
> &nbsp;&nbsp;├── `Dockerfile` — Конфигурация Docker-образа для контейнеризации приложения \
> &nbsp;&nbsp;├── `README.md` — Документация проекта \
> &nbsp;&nbsp;├── `bot.py` — Точка входа бота: инициализация диспетчера, запуск поллинга/вебхуков\
> &nbsp;&nbsp;├── `config.py` —  Настройки приложения: токен бота, параметры подключения к БД, конфигурация логгера\
> &nbsp;&nbsp;├── `docker-compose.yml` —  Файл с описанием сервисов (бот и Redis)\
> &nbsp;&nbsp;├── `entrypoint.sh` —  Скрипт проверки переменных и запуска бота\
> &nbsp;&nbsp;├── `handlers.py` —  Обработчики команд и сообщений пользователя\
> &nbsp;&nbsp;├── `middlewares.py` —  Промежуточное ПО: троттлинг, логирование запросов, обработка ошибок\
> &nbsp;&nbsp;├── `pyproject.toml` —  Управление зависимостями и метаданными проекта (Poetry)\
> &nbsp;&nbsp;└── `uv.lock` —  Фиксированные версии зависимостей (uv package manager)



## Настройка и запуск
### Запуск через чистый Docker
1. Склонируйте репозиторий:
   ```bash
   git clone https://github.com/Kseniya-5/VKR.git
   cd VKR/Fashion_Bot
   ```
2. Убедитесь, что создали файл .env
   
3. Соберите Docker-образ для linux:
   ```bash
   sudo docker build -t fashion-bot .
   ```

4. Запустите контейнер:
   ```bash
   sudo docker run -d --env-file .env --name my-fashion-bot fashion-bot
   ```

5. Провер логи
   ```bash
   sudo docker logs my-fashion-bot
   ```
   
### Если нужно пересобрать Docker-образ

6. Удали старый контейнер
   ```bash
   sudo docker rm my-fashion-bot
   ```

7. Повтори пункты 3-5.

### Запуск через Docker Compose
1. Убедитесь, что находитесь в папке проекта и файл .env создан
2. Поднимите окружение
   ```bash
   sudo docker-compose up --build -d
   ```

3. Проверка статусов контейнеров
    ```bash
   sudo docker-compose ps
   ```
<img width="1110" height="165" alt="image" src="https://github.com/user-attachments/assets/10b26700-de0c-4466-9232-c81bb3e371f9" />

    
4. Логи всех сервисов (полезно для поиска ошибок)
    ```bash
   sudo docker-compose logs -f
   ```
5. Остановка проекта
    ```bash
   sudo docker-compose down
   ```


   
