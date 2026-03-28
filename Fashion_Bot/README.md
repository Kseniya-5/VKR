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
> &nbsp;&nbsp;├── `task.py` —  Celery-воркер: логика долгих задач и обновление статусов в БД\
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

<<<<<<< checkpoint_2_ks
5. Проверка логов
   ```bash
   sudo docker logs my-fashion-bot
=======
2. Соберите Docker-образ для linux:
   ```bash
   sudo docker build -t fashion-bot .
>>>>>>> main
   ```
   
### Если нужно пересобрать Docker-образ

6. Удалите старый контейнер
   ```bash
<<<<<<< checkpoint_2_ks
   sudo docker rm my-fashion-bot
   ```

7. Повторите пункты 3-5.

### Запуск через Docker Compose
1. Убедитесь, что находитесь в папке проекта и файл .env создан
2. Поднимите окружение
   ```bash
   sudo docker-compose up --build -d
   ```
3. Проверьте статус контейнеров
    ```bash
   sudo docker-compose ps
   ```
<img width="1110" height="165" alt="image" src="https://github.com/user-attachments/assets/10b26700-de0c-4466-9232-c81bb3e371f9" />
    
4. Логи всех сервисов (полезно для поиска ошибок)
    ```bash
   sudo docker-compose logs -f
   ```
5. Остановите проект
    ```bash
   sudo docker-compose down
   ```

### Жесткий перезапуск Docker
1. Если не помогло ...
   ```bash
   sudo reboot
   ```
2. Очистка старых зависших контейнеров
   ```bash
   sudo docker-compose down
   ```
3.  Запуск с новыми настройками
   ```bash
   sudo docker-compose up --build -d
   ```

## Проверка асинхронной работы
1. После успешного запуска через docker-compose и проверки запуска контейнеров в терминале можно увидеть следующее:
<img width="2031" height="168" alt="image" src="https://github.com/user-attachments/assets/a3cd2651-9968-4544-b7b4-66e253d55888" />

2. После этого Вы можете проверить работу очереди задач в Telegram (мой бот @FashionableSelectionBot):
<img width="1460" height="997" alt="image" src="https://github.com/user-attachments/assets/fd4ae74f-82c6-492a-9f48-f11c77eebbcc" />

3. И эти данные добавились в таблицу model_tasks моей БД
<img width="1482" height="188" alt="image" src="https://github.com/user-attachments/assets/d7de4ab6-23c5-43f1-b02c-e228d2154c66" />


   
=======
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
>>>>>>> main
