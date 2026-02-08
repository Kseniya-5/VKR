# Dockerfile на тесте 
FROM python:3.10-slim

WORKDIR /app

# Копируем зависимости
COPY pyproject.toml .
RUN pip install --no-cache-dir -U pip uv && \
    uv pip install --system --no-cache-dir aiogram python-dotenv

# Копируем код
COPY src/ ./src/

# Запуск
CMD ["python", "main.py"]
