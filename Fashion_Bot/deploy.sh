#!/bin/bash

set -e

PORT_FORWARD_DB_PID_FILE=".db-port-forward.pid"
PORT_FORWARD_API_PID_FILE=".api-port-forward.pid"

DB_LOCAL_PORT=5433
DB_REMOTE_PORT=5432
DB_SERVICE_NAME="db"

API_SERVICE_NAME="fashion-api-service"
API_LOCAL_PORT=8000
API_REMOTE_PORT=8000

echo "🚀 Начинаем деплой проекта в Minikube..."

# 1. Minikube
if ! minikube status | grep -q "Running"; then
    echo "📦 Запускаем Minikube..."
    minikube start
fi

echo "🐳 Переключаем Docker-окружение на Minikube..."
eval "$(minikube docker-env)"

# 2. Сборка образа приложения
echo "🔨 Собираем Docker-образ приложения (FastAPI + бот + воркер)..."
docker build -t fashion-bot:latest .

# 3. Секреты и конфиги

echo "🗑 Удаляем старые секреты и конфиги (если есть)..."
kubectl delete secret fashion-secrets --ignore-not-found=true
kubectl delete configmap nginx-config --ignore-not-found=true
kubectl delete configmap db-init-configmap --ignore-not-found=true
kubectl delete secret nginx-basic-auth --ignore-not-found=true
kubectl delete secret ghcr-secret --ignore-not-found=true
kubectl delete job db-migration --ignore-not-found=true

echo "🔑 Создаем секреты из .env..."
kubectl create secret generic fashion-secrets --from-env-file=.env

echo "🛡 Настройка Basic Auth для Nginx..."
AUTH_USER=$(grep '^NGINX_AUTH_USER=' .env | cut -d '=' -f2-)
AUTH_PASS=$(grep '^NGINX_AUTH_PASSWORD=' .env | cut -d '=' -f2-)

if [ -n "$AUTH_USER" ] && [ -n "$AUTH_PASS" ]; then
    echo "Генерация htpasswd файла для пользователя $AUTH_USER..."
    htpasswd -c -b auth "$AUTH_USER" "$AUTH_PASS"
    kubectl create secret generic nginx-basic-auth --from-file=auth
    rm -f auth
    echo "✅ Секрет nginx-basic-auth успешно создан!"
else
    echo "⚠️ ВНИМАНИЕ: Переменные NGINX_AUTH_USER или NGINX_AUTH_PASSWORD не найдены в .env"
    echo "⚠️ Basic Auth может не работать."
fi

echo "⚙️ Создаем ConfigMap для Nginx..."
kubectl create configmap nginx-config --from-file=nginx/nginx.conf

echo "🗄 Создаем ConfigMap с SQL-миграцией..."
kubectl create configmap db-init-configmap --from-file=migrations/001_initial.sql

echo "📥 Подгружаем переменные из .env..."
set -a
source .env
set +a

echo "🐳 Создаем секрет для Docker Registry (GHCR)..."
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username="$GHCR_USERNAME" \
  --docker-password="$GHCR_TOKEN"

# 4. Применяем манифесты
echo "📂 Применяем k8s манифесты..."
kubectl apply -f k8s/

echo "⏳ Ждем готовности PostgreSQL StatefulSet..."
kubectl rollout status statefulset/db --timeout=180s

echo "⏳ Ждем завершения миграции базы данных..."
kubectl wait --for=condition=complete job/db-migration --timeout=180s

echo "🔄 Перезапускаем deployment'ы для применения новых настроек..."
kubectl rollout restart deployment/nginx || true
kubectl rollout restart deployment/telegram-bot || true
kubectl rollout restart deployment/worker || true
kubectl rollout restart deployment/fashion-api || true

echo "⏳ Ждем готовности deployment/fashion-api..."
kubectl rollout status deployment/fashion-api --timeout=180s || {
  echo "❌ deployment/fashion-api не стал готовым"
  exit 1
}

# 5. Port-forward'ы для локальной проверки

echo "🧹 Останавливаем старые port-forward'ы, если они были..."

if [ -f "$PORT_FORWARD_DB_PID_FILE" ]; then
    OLD_PID=$(cat "$PORT_FORWARD_DB_PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        kill "$OLD_PID" || true
        echo "ℹ️ Старый DB port-forward остановлен (PID: $OLD_PID)"
    fi
    rm -f "$PORT_FORWARD_DB_PID_FILE"
fi

if [ -f "$PORT_FORWARD_API_PID_FILE" ]; then
    OLD_PID=$(cat "$PORT_FORWARD_API_PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1; then
        kill "$OLD_PID" || true
        echo "ℹ️ Старый API port-forward остановлен (PID: $OLD_PID)"
    fi
    rm -f "$PORT_FORWARD_API_PID_FILE"
fi

echo "🔌 Поднимаем port-forward для PostgreSQL на 127.0.0.1:${DB_LOCAL_PORT} ..."
nohup kubectl port-forward "svc/${DB_SERVICE_NAME}" "${DB_LOCAL_PORT}:${DB_REMOTE_PORT}" > /dev/null 2>&1 &
echo $! > "$PORT_FORWARD_DB_PID_FILE"

sleep 2

if ps -p "$(cat "$PORT_FORWARD_DB_PID_FILE")" > /dev/null 2>&1; then
    echo "✅ DB port-forward успешно запущен"
else
    echo "❌ Не удалось запустить DB port-forward"
    exit 1
fi

echo "🔌 Поднимаем port-forward для API на 127.0.0.1:${API_LOCAL_PORT} ..."
nohup kubectl port-forward "svc/${API_SERVICE_NAME}" "${API_LOCAL_PORT}:${API_REMOTE_PORT}" > /dev/null 2>&1 &
echo $! > "$PORT_FORWARD_API_PID_FILE"

sleep 2

if ps -p "$(cat "$PORT_FORWARD_API_PID_FILE")" > /dev/null 2>&1; then
    echo "✅ API port-forward успешно запущен"
else
    echo "❌ Не удалось запустить API port-forward"
    exit 1
fi

echo "✅ Деплой и настройка окружения для проверки успешно завершены!"
echo "**********************************************************************************"
echo "🌐 Nginx: minikube service nginx-service --url"
echo "🧪 FastAPI Swagger: http://127.0.0.1:${API_LOCAL_PORT}/docs"
echo "⏰ Статус подов: kubectl get pods"
echo "🛠 Сервисы: kubectl get services"
echo " "
echo "🛑 Для остановки сервисов в Kubernetes: ./stop.sh"
