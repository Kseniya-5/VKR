FROM python:3.12-slim AS builder

WORKDIR /app

RUN pip install --no-cache-dir uv
COPY pyproject.toml uv.lock README.md ./

RUN uv pip install --system --no-cache-dir --compile-bytecode .

FROM python:3.12-slim

WORKDIR /app

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

COPY --from=builder --chown=appuser:appuser /usr/local /usr/local

COPY --chown=appuser:appuser . .

ENV PYTHONUNBUFFERED=1

RUN chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
