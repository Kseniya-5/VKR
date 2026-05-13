#!/bin/bash

set -e

PORT_FORWARD_PID_FILE=".db-port-forward.pid"

echo "🛑 Останавливаем сервисы в Kubernetes..."

echo "🔌 Останавливаем port-forward PostgreSQL..."
if [ -f "$PORT_FORWARD_PID_FILE" ]; then
    PID=$(cat "$PORT_FORWARD_PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        kill "$PID" || true
        echo "✅ Port-forward остановлен (PID: $PID)"
    else
        echo "ℹ️ Port-forward уже не запущен"
    fi
    rm -f "$PORT_FORWARD_PID_FILE"
else
    echo "ℹ️ PID-файл port-forward не найден"
fi

echo "📂 Удаляем ресурсы Kubernetes..."
kubectl delete -f k8s/ --ignore-not-found=true || true

echo "🧹 Удаляем секреты и конфиги..."
kubectl delete secret fashion-secrets --ignore-not-found=true || true
kubectl delete secret ghcr-secret --ignore-not-found=true || true
kubectl delete secret nginx-basic-auth --ignore-not-found=true || true
kubectl delete configmap nginx-config --ignore-not-found=true || true
kubectl delete configmap db-init-configmap --ignore-not-found=true || true

echo "⏸️ Останавливаем Minikube..."
minikube stop || true

echo "✅ Все ресурсы удалены! Кластер остановлен и очищен."
echo "**********************************************************************************"
echo "🚀 Для запуска сервисов в Kubernetes используйте: ./deploy.sh"