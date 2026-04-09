# Fashion_CV (ML-ядро) — ML pipeline

В этом шаге мы вынесли всю работу по **Этапу 1 (salient object detection / background removal)** в отдельный модуль пайплайна:

- `Fashion_CV/ml_pipeline/1_salient_object_detection/` — самодостаточный шаг предобработки, который удаляет фон у пользовательских фото через `rembg` (U2Net) и сохраняет результат с прозрачностью или на белом/чёрном фоне.

Зачем это нужно: привести домашние фотографии к более «датасетному» виду — выделить предмет одежды и убрать фон, чтобы дальше (в следующих этапах) было проще делать сегментацию/классификацию/поиск похожих вещей.

## Структура шага

Папка шага: `Fashion_CV/ml_pipeline/1_salient_object_detection/`

- Входные фото: `data/images_raw/`
- Результаты (без фона): `data/images_nobg/`
- Веса/кеш модели: `models/rembg/` (проект принудительно направляет `rembg` кеш в эту папку через `U2NET_HOME`)

## Запуск (uv)

```bash
cd Fashion_CV/ml_pipeline/1_salient_object_detection

# (опционально) если в окружении проблемы с кешем в ~/.cache (read-only), используйте /tmp:
export UV_CACHE_DIR=/tmp/uv-cache

# создать venv (важно: `rembg[gpu]` тянет `onnxruntime-gpu`, а его колёса на Linux
# доступны начиная с Python 3.11; для Python 3.14 часто ещё нет готовых wheels)
uv python install 3.12
uv venv --python 3.12 --clear

# установить зависимости из pyproject.toml
uv sync

# (опционально) активировать виртуальное окружение (если хочешь запускать python/pip напрямую)
source .venv/bin/activate

# деактивировать окружение
deactivate
```

## Запуск CLI

```bash
# 1) один файл -> один файл (прозрачный фон по умолчанию)
uv run fashion-cv remove-bg --input path/to/image.jpg --output out.png

# 2) белый фон
uv run fashion-cv remove-bg --input path/to/image.jpg --output out.png --background white

# 2.1) чёрный фон
uv run fashion-cv remove-bg --input path/to/image.jpg --output out.png --background black

# 3) папка -> папка (с сохранением структуры)
uv run fashion-cv remove-bg --input path/to/in_dir --output path/to/out_dir --recursive

# 3.1) пример для структуры шага
uv run fashion-cv remove-bg --input data/images_raw --output data/images_nobg --recursive

# 4) (опционально) указать свою папку с весами
uv run fashion-cv remove-bg --input path/to/image.jpg --output out.png --model-dir ./models/rembg
```

Примечание: `rembg` при первом запуске может скачивать веса модели (нужен интернет). Если интернета нет, можно заранее положить `u2net.onnx` в `models/rembg/`.

## Проверка, что onnxruntime видит GPU

```bash
uv run python -c "import onnxruntime as ort; print('onnxruntime device:', ort.get_device())"
```

Если вывод `GPU`, то backend установлен корректно. Если `CPU` или импорт падает — проверь наличие NVIDIA GPU/драйвера/CUDA, либо переключись на CPU-вариант зависимостей.
