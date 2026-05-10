#!/usr/bin/env bash

set -Eeuo pipefail

PORT_FORWARD_DB_PID_FILE=".db-port-forward.pid"
PORT_FORWARD_API_PID_FILE=".api-port-forward.pid"
PORT_FORWARD_NGINX_PID_FILE=".nginx-port-forward.pid"

PORT_FORWARD_DB_LOG_FILE=".db-port-forward.log"
PORT_FORWARD_API_LOG_FILE=".api-port-forward.log"
PORT_FORWARD_NGINX_LOG_FILE=".nginx-port-forward.log"

DB_LOCAL_PORT="${DB_LOCAL_PORT:-5433}"
DB_REMOTE_PORT="${DB_REMOTE_PORT:-5432}"
DB_SERVICE_NAME="${DB_SERVICE_NAME:-db}"

API_SERVICE_NAME="${API_SERVICE_NAME:-fashion-api-service}"
API_LOCAL_PORT="${API_LOCAL_PORT:-8000}"
API_REMOTE_PORT="${API_REMOTE_PORT:-8000}"

NGINX_SERVICE_NAME="${NGINX_SERVICE_NAME:-nginx-service}"
NGINX_LOCAL_PORT="${NGINX_LOCAL_PORT:-8080}"
NGINX_REMOTE_PORT="${NGINX_REMOTE_PORT:-80}"

HARD_PRUNE="${HARD_PRUNE:-1}"
PRUNE_VOLUMES="${PRUNE_VOLUMES:-0}"
SKIP_NGINX_BUILD="${SKIP_NGINX_BUILD:-0}"
DOCKER_PROGRESS="${DOCKER_PROGRESS:-plain}"

log() {
    echo
    echo "--------------------------------------------------------------------------------"
    echo "$1"
    echo "--------------------------------------------------------------------------------"
}

step() { echo "➡️  $1"; }
warn() { echo "⚠️  $1"; }
fail() { echo "❌ $1"; exit 1; }
command_exists() { command -v "$1" >/dev/null 2>&1; }

require_file() {
    local file="$1"
    local message="$2"
    [ -f "$file" ] || fail "Не найден файл: ${file}. ${message}"
}

require_dir() {
    local dir="$1"
    local message="$2"
    [ -d "$dir" ] || fail "Не найдена папка: ${dir}. ${message}"
}

stop_port_forward_by_pid_file() {
    local pid_file="$1"
    local name="$2"

    if [ -f "$pid_file" ]; then
        local old_pid
        old_pid="$(cat "$pid_file" 2>/dev/null || true)"
        if [ -n "$old_pid" ] && ps -p "$old_pid" >/dev/null 2>&1; then
            kill "$old_pid" || true
            step "Старый ${name} port-forward остановлен, PID=${old_pid}"
        fi
        rm -f "$pid_file"
    fi
}

wait_for_port_forward() {
    local pid_file="$1"
    local name="$2"
    local log_file="$3"

    sleep 2

    if [ -f "$pid_file" ] && ps -p "$(cat "$pid_file")" >/dev/null 2>&1; then
        step "${name} port-forward запущен"
        return 0
    fi

    echo "❌ Не удалось запустить ${name} port-forward. Лог:"
    cat "$log_file" 2>/dev/null || true
    exit 1
}

get_container_name() {
    local deployment="$1"
    kubectl get deployment "$deployment" -o jsonpath='{.spec.template.spec.containers[0].name}'
}

set_deployment_image() {
    local deployment="$1"
    local image="$2"

    if ! kubectl get deployment "$deployment" >/dev/null 2>&1; then
        warn "Deployment ${deployment} не найден, пропускаю"
        return 0
    fi

    local container_name
    container_name="$(get_container_name "$deployment")"

    step "${deployment}: container=${container_name}, image=${image}"
    kubectl rollout resume "deployment/${deployment}" >/dev/null 2>&1 || true
    kubectl set image "deployment/${deployment}" "${container_name}=${image}"
}

restart_and_wait_deployment() {
    local deployment="$1"

    if ! kubectl get deployment "$deployment" >/dev/null 2>&1; then
        warn "Deployment ${deployment} не найден, пропускаю"
        return 0
    fi

    kubectl rollout resume "deployment/${deployment}" >/dev/null 2>&1 || true
    kubectl rollout restart "deployment/${deployment}"
    kubectl rollout status "deployment/${deployment}" --timeout=300s
}

purge_python_cache() {
    step "pip cache purge"
    if command_exists python3; then
        python3 -m pip cache purge || true
    elif command_exists python; then
        python -m pip cache purge || true
    else
        warn "python3/python не найден. Пропускаю pip cache purge"
    fi
}

purge_local_project_cache() {
    step "Удаляем локальные build/cache папки проекта"
    rm -rf .pytest_cache .ruff_cache .mypy_cache build dist .cache htmlcov || true
    rm -rf ./*.egg-info || true
    find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find . -type f -name "*.pyc" -delete 2>/dev/null || true
    find . -type f -name "*.pyo" -delete 2>/dev/null || true
}

hard_cleanup() {
    log "🧹 Чистим Docker/BuildKit/uv/pip cache, чтобы разгрузить WSL"

    if [ "$HARD_PRUNE" != "1" ]; then
        step "HARD_PRUNE=0, очистка пропущена"
        return 0
    fi

    eval "$(minikube docker-env -u)" >/dev/null 2>&1 || true

    step "docker builder prune -a -f"
    docker builder prune -a -f || true

    step "docker buildx prune -a -f"
    docker buildx prune -a -f || true

    if [ "$PRUNE_VOLUMES" = "1" ]; then
        warn "Включена жёсткая очистка Docker volumes: docker system prune -a --volumes -f"
        docker system prune -a --volumes -f || true
    else
        step "docker system prune -a -f без volumes"
        docker system prune -a -f || true
    fi

    step "uv cache clean"
    if command_exists uv; then
        uv cache clean || true
    else
        warn "uv не найден в PATH. Пропускаю uv cache clean"
    fi

    purge_python_cache
    purge_local_project_cache

    step "Проверка свободного места"
    df -h . || true
}

create_or_update_configmaps_and_secrets() {
    log "🔑 Обновляем секреты и ConfigMap'ы"

    if [ -f ".env" ]; then
        kubectl delete secret fashion-secrets --ignore-not-found=true
        kubectl create secret generic fashion-secrets --from-env-file=.env
    else
        warn ".env не найден. Secret fashion-secrets не пересоздан"
    fi

    kubectl delete configmap nginx-config --ignore-not-found=true
    if [ -f "nginx/nginx.conf" ]; then
        kubectl create configmap nginx-config --from-file=nginx/nginx.conf
    fi

    kubectl delete configmap db-init-configmap --ignore-not-found=true
    kubectl delete configmap db-migration-sql --ignore-not-found=true
    require_file "migrations/001_initial.sql" "Нужен объединённый файл миграции 001_initial.sql"
    kubectl create configmap db-init-configmap --from-file=001_initial.sql=migrations/001_initial.sql
    kubectl create configmap db-migration-sql --from-file=001_initial.sql=migrations/001_initial.sql

    if [ -f ".env" ]; then
        set -a
        # shellcheck disable=SC1091
        source .env
        set +a

        if [ -n "${GHCR_USERNAME:-}" ] && [ -n "${GHCR_TOKEN:-}" ]; then
            kubectl delete secret ghcr-secret --ignore-not-found=true
            kubectl create secret docker-registry ghcr-secret \
                --docker-server=ghcr.io \
                --docker-username="${GHCR_USERNAME}" \
                --docker-password="${GHCR_TOKEN}"
        else
            step "GHCR_USERNAME/GHCR_TOKEN не найдены, ghcr-secret пропущен"
        fi

        if [ -n "${NGINX_AUTH_USER:-}" ] && [ -n "${NGINX_AUTH_PASSWORD:-}" ] && command_exists htpasswd; then
            kubectl delete secret nginx-basic-auth --ignore-not-found=true
            htpasswd -c -b auth "${NGINX_AUTH_USER}" "${NGINX_AUTH_PASSWORD}"
            kubectl create secret generic nginx-basic-auth --from-file=auth
            rm -f auth
        else
            step "nginx-basic-auth пропущен"
        fi
    fi
}

find_db_pod() {
    local db_pod
    db_pod="$(kubectl get pods -l app=db -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"

    if [ -z "$db_pod" ]; then
        db_pod="$(kubectl get pods -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' | grep -E '^db-[0-9]+$' | head -1 || true)"
    fi

    [ -n "$db_pod" ] || fail "Не удалось найти pod PostgreSQL. Проверь: kubectl get pods --show-labels"
    echo "$db_pod"
}

verify_database_schema() {
    log "🧪 Проверяем схему БД после единой миграции"

    local db_pod
    db_pod="$(find_db_pod)"
    step "PostgreSQL pod: ${db_pod}"
    kubectl wait --for=condition=Ready "pod/${db_pod}" --timeout=240s || true

    # ВАЖНО: здесь нельзя писать -c "\nSELECT ...", потому что psql получает буквальный \n
    # и воспринимает его как meta-command. Поэтому используем однострочный SQL.
    local users_count
    users_count="$(kubectl exec "$db_pod" -- sh -lc "PGPASSWORD=\"\$POSTGRES_PASSWORD\" psql -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -tAc \"SELECT count(*) FROM information_schema.columns WHERE table_name='users' AND column_name IN ('first_name','last_name');\"")"
    users_count="$(echo "$users_count" | tr -d '[:space:]')"

    if [ "$users_count" != "2" ]; then
        fail "В таблице users нет first_name/last_name. Проверь migrations/001_initial.sql"
    fi
    step "users.first_name / users.last_name найдены"

    local reset_count
    reset_count="$(kubectl exec "$db_pod" -- sh -lc "PGPASSWORD=\"\$POSTGRES_PASSWORD\" psql -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -tAc \"SELECT count(*) FROM information_schema.columns WHERE table_name='password_reset_tokens' AND column_name IN ('telegram_chat_id','telegram_message_id','telegram_message_deleted_at');\"")"
    reset_count="$(echo "$reset_count" | tr -d '[:space:]')"

    if [ "$reset_count" != "3" ]; then
        fail "В password_reset_tokens нет telegram_* полей. Проверь migrations/001_initial.sql"
    fi
    step "password_reset_tokens telegram_* поля найдены"
}

start_port_forward() {
    log "🔌 Поднимаем port-forward'ы для локальной проверки"

    nohup kubectl port-forward "svc/${DB_SERVICE_NAME}" "${DB_LOCAL_PORT}:${DB_REMOTE_PORT}" >"${PORT_FORWARD_DB_LOG_FILE}" 2>&1 &
    echo $! >"${PORT_FORWARD_DB_PID_FILE}"
    wait_for_port_forward "${PORT_FORWARD_DB_PID_FILE}" "DB" "${PORT_FORWARD_DB_LOG_FILE}"

    nohup kubectl port-forward "svc/${API_SERVICE_NAME}" "${API_LOCAL_PORT}:${API_REMOTE_PORT}" >"${PORT_FORWARD_API_LOG_FILE}" 2>&1 &
    echo $! >"${PORT_FORWARD_API_PID_FILE}"
    wait_for_port_forward "${PORT_FORWARD_API_PID_FILE}" "API" "${PORT_FORWARD_API_LOG_FILE}"

    nohup kubectl port-forward "svc/${NGINX_SERVICE_NAME}" "${NGINX_LOCAL_PORT}:${NGINX_REMOTE_PORT}" >"${PORT_FORWARD_NGINX_LOG_FILE}" 2>&1 &
    echo $! >"${PORT_FORWARD_NGINX_PID_FILE}"
    wait_for_port_forward "${PORT_FORWARD_NGINX_PID_FILE}" "Nginx" "${PORT_FORWARD_NGINX_LOG_FILE}"
}

log "🚀 Начинаем жёсткий деплой Fashion Bot в Minikube"

require_file "Dockerfile" "Запускай скрипт из корня Fashion_Bot/"
require_dir "app" "Запускай скрипт из корня Fashion_Bot/"
require_dir "k8s" "Запускай скрипт из корня Fashion_Bot/"
require_dir "nginx" "Запускай скрипт из корня Fashion_Bot/"
require_file "migrations/001_initial.sql" "Сначала положи объединённую миграцию в migrations/001_initial.sql"

log "🧹 Останавливаем старые port-forward'ы"
stop_port_forward_by_pid_file "${PORT_FORWARD_DB_PID_FILE}" "DB"
stop_port_forward_by_pid_file "${PORT_FORWARD_API_PID_FILE}" "API"
stop_port_forward_by_pid_file "${PORT_FORWARD_NGINX_PID_FILE}" "Nginx"

log "📦 Проверяем Minikube"
if ! minikube status >/dev/null 2>&1; then
    step "Запускаем Minikube"
    minikube start
else
    step "Minikube уже запущен"
fi

hard_cleanup

log "🏷 Создаём уникальные теги образов"
TAG="${TAG:-$(date +%Y%m%d%H%M%S)}"
BOT_IMAGE="${BOT_IMAGE:-fashion-bot:${TAG}}"
NGINX_IMAGE="${NGINX_IMAGE:-fashion-nginx:${TAG}}"

echo "BOT_IMAGE=${BOT_IMAGE}"
echo "NGINX_IMAGE=${NGINX_IMAGE}"

log "🔨 Собираем backend/bot/worker image"
eval "$(minikube docker-env -u)" >/dev/null 2>&1 || true
docker build --no-cache --progress="${DOCKER_PROGRESS}" -t "${BOT_IMAGE}" .
minikube image load "${BOT_IMAGE}"

if [ "$SKIP_NGINX_BUILD" = "1" ]; then
    warn "SKIP_NGINX_BUILD=1, nginx image не пересобирается"
else
    log "🔨 Собираем nginx/frontend image"
    docker build --no-cache --progress="${DOCKER_PROGRESS}" -t "${NGINX_IMAGE}" ./nginx
    minikube image load "${NGINX_IMAGE}"
fi

create_or_update_configmaps_and_secrets

log "📂 Применяем k8s манифесты"
kubectl delete job db-migration --ignore-not-found=true
kubectl apply -f k8s/

log "🖼 Подставляем новые image tags в Kubernetes"
kubectl get deploy
set_deployment_image "fashion-api" "${BOT_IMAGE}"
set_deployment_image "telegram-bot" "${BOT_IMAGE}"
set_deployment_image "worker" "${BOT_IMAGE}"

if [ "$SKIP_NGINX_BUILD" != "1" ]; then
    set_deployment_image "nginx" "${NGINX_IMAGE}"
fi

log "🗄 Проверяем PostgreSQL и единую миграцию"
kubectl rollout status statefulset/db --timeout=240s || true
kubectl wait --for=condition=complete job/db-migration --timeout=240s || true
verify_database_schema

log "🔄 Принудительно перезапускаем deployment'ы"
restart_and_wait_deployment "fashion-api"
restart_and_wait_deployment "telegram-bot"
restart_and_wait_deployment "worker"
restart_and_wait_deployment "nginx"

log "🔎 Проверяем образы в deployment'ах"
kubectl get deployment fashion-api -o jsonpath='{.spec.template.spec.containers[*].image}{"\n"}' || true
kubectl get deployment telegram-bot -o jsonpath='{.spec.template.spec.containers[*].image}{"\n"}' || true
kubectl get deployment worker -o jsonpath='{.spec.template.spec.containers[*].image}{"\n"}' || true
kubectl get deployment nginx -o jsonpath='{.spec.template.spec.containers[*].image}{"\n"}' || true

start_port_forward

log "🌐 Проверяем маршруты через Nginx"
curl -i "http://localhost:${NGINX_LOCAL_PORT}/" | head -40 || true
echo
curl -i "http://localhost:${NGINX_LOCAL_PORT}/api/health" | head -40 || true

log "✅ Жёсткий деплой завершён"
echo "BOT_IMAGE=${BOT_IMAGE}"
echo "NGINX_IMAGE=${NGINX_IMAGE}"
echo
echo "🌐 Web:              http://localhost:${NGINX_LOCAL_PORT}/"
echo "🧪 API docs:         http://localhost:${API_LOCAL_PORT}/docs"
echo "🧪 API via Nginx:    http://localhost:${NGINX_LOCAL_PORT}/api/health"
echo "🗄 PostgreSQL local: 127.0.0.1:${DB_LOCAL_PORT}"
echo
echo "📌 Полезные команды:"
echo "kubectl get pods"
echo "kubectl logs deployment/fashion-api --tail=100"
echo "kubectl logs deployment/telegram-bot --tail=100 -f"
echo "kubectl logs deployment/worker --tail=100 -f"
echo
echo "🛑 Остановить port-forward'ы:"
echo "kill \$(cat ${PORT_FORWARD_DB_PID_FILE}) \$(cat ${PORT_FORWARD_API_PID_FILE}) \$(cat ${PORT_FORWARD_NGINX_PID_FILE})"
