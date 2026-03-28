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
   # Токен вашего Telegram-бота (ОБЯЗАТЕЛЬНО ЗАМЕНИТЬ)
   BOT_TOKEN=ваш_токен_из_BotFather
   
   # Настройки для брокера сообщений Celery (оставить по умолчанию для docker-compose)
   REDIS_URL=redis://redis:6379/0
   
   # Учетные данные для базы данных PostgreSQL (задайте свои значения)
   POSTGRES_USER=ваш_пользователь_БД
   POSTGRES_PASSWORD=ваш_пароль_БД
   POSTGRES_DB=название_вашей_БД
   
   # Строка подключения для Python-приложения (должна совпадать с данными выше)
   DATABASE_URL=postgresql://ваш_пользователь_БД:ваш_пароль_БД@db:5432/название_вашей_БД
   ```

#### Как получить токен бота?
1. Свяжитесь с @BotFather
2. Выполните команду /newbot и следуйте инструкциям, пока вам не будет выдан новый токен

## Структура проекта
> `Fashion_Bot/` \
> &nbsp;&nbsp;│── `k8s/` — ... \
> &nbsp;&nbsp;│&nbsp;&nbsp; ├── `bot.yaml` — ... \
> &nbsp;&nbsp;│&nbsp;&nbsp; ├── `configmap.yaml` — ... \
> &nbsp;&nbsp;│&nbsp;&nbsp; ├── `bd-init-configmap.yaml` — ... \
> &nbsp;&nbsp;│&nbsp;&nbsp; ├── `nginx.yaml` — ... \
> &nbsp;&nbsp;│&nbsp;&nbsp; ├── `postgres.yaml` — ... \
> &nbsp;&nbsp;│&nbsp;&nbsp; ├── `redis.yaml` — ... \
> &nbsp;&nbsp;│ &nbsp;&nbsp;└── `worker.yaml` — ... \
> &nbsp;&nbsp;│── `nginx/` — Папка с конфигурацией Nginx сервера \
> &nbsp;&nbsp;│&nbsp;&nbsp; ├── `Dockerfile` — Сборка образа Nginx \
> &nbsp;&nbsp;│ &nbsp;&nbsp;└── `nginx.conf` — Настройки Reverse proxy и отдачи статики \
> &nbsp;&nbsp;├── `.gitignore` — Игнорируемые файлы \
> &nbsp;&nbsp;├── `Dockerfile` — Конфигурация Docker-образа для контейнеризации приложения \
> &nbsp;&nbsp;├── `README.md` — Документация проекта \
> &nbsp;&nbsp;├── `bot.py` — Точка входа бота: инициализация диспетчера, запуск поллинга/вебхуков\
> &nbsp;&nbsp;├── `config.py` —  Настройки приложения: токен бота, параметры подключения к БД, конфигурация логгера\
> &nbsp;&nbsp;├── `docker-compose.yml` —  Файл с описанием сервисов (бот и Redis)\
> &nbsp;&nbsp;├── `entrypoint.sh` —  Скрипт проверки переменных и запуска бота\
> &nbsp;&nbsp;├── `handlers.py` —  Обработчики команд и сообщений пользователя\
> &nbsp;&nbsp;├── `init.sql` —  ...\
> &nbsp;&nbsp;├── `middlewares.py` —  Промежуточное ПО: троттлинг, логирование запросов, обработка ошибок\
> &nbsp;&nbsp;├── `pyproject.toml` —  Управление зависимостями и метаданными проекта (Poetry)\
> &nbsp;&nbsp;├── `task.py` —  Celery-воркер: логика долгих задач и обновление статусов в БД\
> &nbsp;&nbsp;├── `uv.lock` —  Фиксированные версии зависимостей (uv package manager)\
> &nbsp;&nbsp;└── `web_app.py` —  Простой aiohttp веб-сервер для связи с Nginx (Production mode)

***

## Настройка и запуск
### 1. Запуск через чистый Docker
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

5. Проверка логов
   ```bash
   sudo docker logs my-fashion-bot
   ```
   
#### Если нужно пересобрать Docker-образ

6. Удалите старый контейнер
   ```bash
   sudo docker rm my-fashion-bot
   ```

7. Повторите пункты 3-5.

***

### 2. Запуск через Docker Compose (Полное Production окружение)
Этот способ поднимает всю архитектуру: бота, веб-сервер, Nginx (Reverse Proxy), Redis, БД и Celery-воркер.
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

#### Жесткий перезапуск Docker
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
***

### 3. Запуск проекта через Kubernetes (Полное Production окружение)
Проект полностью адаптирован для работы в Kubernetes-кластере с использованием `Minikube`. Все манифесты находятся в директории `k8s/`
1. Поскольку Minikube работает в изолированной среде, необходимо собрать Docker-образ непосредственно внутри его окружения:
```bash
# 1. Запускаем локальный кластер
minikube start

# 2. Переключаем Docker-окружение терминала на Minikube
eval $(minikube docker-env)

# 3. Собираем образ бота
docker build -t fashion-bot:latest .
```
2. Чтобы не хранить токены и пароли в открытых yaml-манифестах, создаем секреты напрямую из файла `.env`:
```bash
kubectl create secret generic fashion-secrets --from-env-file=.env
```
3. Применяем все подготовленные манифесты (Deployment, Service, ConfigMap) из папки `k8s/`:
```bash
kubectl apply -f k8s/
```
4. Убедитесь, что все компоненты (поды) перешли в статус `Running`. Это может занять около 1-2 минут (при первом запуске скачиваются образы БД и Redis):

```bash
# Проверка статуса подов
kubectl get pods
```
<img width="807" height="199" alt="image" src="https://github.com/user-attachments/assets/b02c1f66-8f74-4b89-98a6-5998d699c6a2" /> <br/>
```bash
# Проверка созданных сервисов
kubectl get services
```
<img width="952" height="197" alt="image" src="https://github.com/user-attachments/assets/d71c392d-597e-4362-8187-4c25e3f25a87" /> <br/>


5. Если нужно проверить логи конкретного компонента:
```bash
# Логи Telegram-бота
kubectl logs deployment/telegram-bot

# Логи Celery-воркера
kubectl logs deployment/worker

# Логи базы данных
kubectl logs deployment/db
```
6. Nginx доступен извне кластера через сервис типа `NodePort`. Чтобы получить прямую ссылку для открытия в браузере, выполните:
```bash
minikube service nginx-service --url
```
#### Управление кластером (Остановка и Перезапуск)
7. Если вы хотите поставить кластер на паузу, сохранив все данные и поды:
```bash
minikube stop
```
8. Если вы внесли изменения в код бота (файлы `.py`):
```bash
# 1. Обязательно убедитесь, что вы в окружении Minikube
eval $(minikube docker-env)

# 2. Соберите новый образ
docker build -t fashion-bot:latest .

# 3. Перезапустите поды, чтобы они подхватили новую версию
kubectl rollout restart deployment telegram-bot worker
```
9. Если нужно удалить все ресурсы (поды, сервисы, секреты), созданные для проекта:
```bash
# Удаляем ресурсы по манифестам
kubectl delete -f k8s/

# Удаляем созданный вручную секрет
kubectl delete secret fashion-secrets
```
***

# Проверка работоспособности
## Проверка асинхронной очереди задач (Celery + Redis + DB)
1. После успешного запуска через docker-compose и проверки запуска контейнеров в терминале можно увидеть следующее:
<img width="2031" height="168" alt="image" src="https://github.com/user-attachments/assets/a3cd2651-9968-4544-b7b4-66e253d55888" />

2. После этого Вы можете проверить работу очереди задач в Telegram (мой бот @FashionableSelectionBot). Задачи принимаются моментально, а их выполнение и изменение статусов происходит в фоновом режиме:
<img width="1460" height="997" alt="image" src="https://github.com/user-attachments/assets/fd4ae74f-82c6-492a-9f48-f11c77eebbcc" />

3. Все изменения статусов надежно сохраняются в базу данных PostgreSQL (model_tasks):
<img width="1482" height="188" alt="image" src="https://github.com/user-attachments/assets/d7de4ab6-23c5-43f1-b02c-e228d2154c66" />

## Проверка Nginx (Reverse Proxy и статика)
Приложение работает в режиме Production (DEBUG=False).
1. После успешного запуска через docker-compose и проверки запуска контейнеров в терминале можно увидеть следующее: <br/> <img width="1280" height="125" alt="image" src="https://github.com/user-attachments/assets/314573e9-67e0-49cd-94ac-43a905dbb3cf" />
2. Откройте браузер и перейдите по адресу <mark> http://localhost:8888 </mark> — Nginx успешно проксирует запрос к приложению и возвращает ответ от веб-сервера бота <br/> <img width="689" height="97" alt="image" src="https://github.com/user-attachments/assets/aa550deb-118a-44a8-9de3-6eb5d7fe1520" />



   
