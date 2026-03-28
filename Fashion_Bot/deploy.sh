#!/bin/bash

set -e

echo "🚀 Начинаем деплой проекта в Minikube..."

if ! minikube status | grep -q "Running"; then
    echo "📦 Запускаем Minikube..."
    minikube start
fi

echo "🐳 Переключаем Docker-окружение на Minikube..."
eval $(minikube docker-env)

echo "🔨 Собираем Docker-образ бота..."
docker build -t fashion-bot:latest .

echo "🗑 Удаляем старые секреты и конфиги (если есть)..."
kubectl delete secret fashion-secrets --ignore-not-found
kubectl delete configmap nginx-config --ignore-not-found
kubectl delete secret nginx-basic-auth --ignore-not-found
kubectl delete job db-migration --ignore-not-found
kubectl delete deployment db --ignore-not-found

echo "🔑 Создаем секреты из .env..."
kubectl create secret generic fashion-secrets --from-env-file=.env

echo "🛡 Настройка Basic Auth для Nginx..."
AUTH_USER=$(grep NGINX_AUTH_USER .env | cut -d '=' -f2)
AUTH_PASS=$(grep NGINX_AUTH_PASSWORD .env | cut -d '=' -f2)
if [ -n "$AUTH_USER" ] && [ -n "$AUTH_PASS" ]; then
    echo "Генерация htpasswd файла для пользователя $AUTH_USER..."
    htpasswd -c -b auth "$AUTH_USER" "$AUTH_PASS"
    kubectl create secret generic nginx-basic-auth --from-file=auth
    rm auth
    echo "Секрет nginx-basic-auth успешно создан!"
else
    echo "⚠️ ВНИМАНИЕ: Переменные NGINX_AUTH_USER или NGINX_AUTH_PASSWORD не найдены в .env!"
    echo "Basic Auth может не работать."
fi

echo "⚙️ Создаем ConfigMap для Nginx..."
kubectl create configmap nginx-config --from-file=nginx/nginx.conf

echo "📥 Подгружаем переменные из .env..."
set -a; source .env; set +a

echo "🐳 Создаем секрет для Docker Registry (GHCR)..."
kubectl delete secret ghcr-secret --ignore-not-found
kubectl create secret docker-registry ghcr-secret \
  --docker-server=ghcr.io \
  --docker-username=$GHCR_USERNAME \
  --docker-password=$GHCR_TOKEN

echo "📂 Применяем k8s манифесты..."
kubectl apply -f k8s/

echo "⏳ Ждем завершения миграции базы данных..."
kubectl wait --for=condition=complete job/db-migration --timeout=120s

echo "🔄 Перезапускаем поды для применения новых настроек..."
kubectl rollout restart deployment nginx telegram-bot worker

echo "✅ Деплой успешно завершен!"

echo "**********************************************************************************"
echo "🌐 Чтобы открыть Nginx, используйте команду: minikube service nginx-service --url"
echo "⏰ Для проверки статуса подов, используйте команду: kubectl get pods"
echo "💾 Для проверки создания диска для БД, используйте команду: kubectl get pvc"
echo "🛠 Для проверки созданных сервисов, используйте команду: kubectl get services"
echo "🛑 Для остановки сервисов в Kubernetes, используйте скрипт, запустив его командой: ./stop.sh"