#!/bin/bash

echo "🛑 Останавливаем сервисы в Kubernetes..."

kubectl delete -f k8s/

echo "🧹 Удаляем секреты и конфиги..."

kubectl delete secret fashion-secrets --ignore-not-found
kubectl delete configmap nginx-config --ignore-not-found
kubectl delete secret ghcr-secret --ignore-not-found
kubectl delete secret nginx-basic-auth --ignore-not-found

echo "⏸️ Останавливаем Minikube..."
minikube stop

echo "✅ Все ресурсы удалены! Кластер остановлен и очищен."
echo "**********************************************************************************"
echo "🚀 Для запуска сервисов в Kubernetes, используйте скрипт, запустив его командой: ./deploy.sh"