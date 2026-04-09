# 1_salient_object_detection (background removal)

Шаг пайплайна, который выделяет основной объект (вещь) на фото и удаляет фон с помощью `rembg` (U2Net).

## Быстрый старт

```bash
cd Fashion_CV/ml_pipeline/1_salient_object_detection

# (опционально) если в окружении проблемы с кешем в ~/.cache (read-only), используйте /tmp:
export UV_CACHE_DIR=/tmp/uv-cache

uv python install 3.12
uv venv --python 3.12 --clear
uv sync
```

## Запуск

```bash
# папка -> папка (с сохранением структуры)
uv run fashion-cv remove-bg --input data/images_raw --output data/images_nobg --recursive

# один файл -> один файл
uv run fashion-cv remove-bg --input path/to/image.jpg --output out.png
```

По умолчанию веса/кеш `rembg` хранятся внутри шага в `models/rembg/` (через `U2NET_HOME`).

