# 1_salient_object_detection — удаление фона (Salient Object Detection)

**Автор:** Герилович Илья

Шаг ML-пайплайна, который выделяет основной объект на пользовательской фотографии (вещь/одежду) и удаляет «шумный» фон.
Реализация основана на библиотеке `rembg` и модели `U2Net` (salient object detection / foreground segmentation).

Результатом является изображение:
- либо с прозрачным фоном,
- либо с однотонным фоном - удобно для дальнейшей нормализации входов и устойчивости последующих моделей.

## Как это используется в пайплайне

Модуль применяется как самый первый этап обработки «домашних» фотографий: он снижает влияние посторонних объектов, сложного фона и неоднородного освещения на последующие шаги (подготовка датасета, извлечение атрибутов и т.д.).

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

## Параметры CLI

```bash
uv run fashion-cv remove-bg --help
```

Ключевые параметры:
- `--background transparent|white|black` — тип фона результата (по умолчанию `transparent`).
- `--model u2net` — модель `rembg` (по умолчанию `u2net`).
- `--model-dir <path>` — куда сохранять веса/кеш `rembg` (если не указан, используется `models/rembg/`).
- `--recursive` — рекурсивно обрабатывать подпапки.

Примечание по формату вывода:
- при `--background transparent` результаты сохраняются как `*.png` (нужен alpha-канал);
- при `white/black` сохраняется исходное расширение (например, `*.jpg`).

## Структура директории шага

```text
1_salient_object_detection/
  src/fashion_cv/
    cli.py                        # точка входа CLI: fashion-cv remove-bg
    preprocess/remove_bg.py        # обёртка над rembg (U2Net), batch-обработка
  data/
    images_raw/                   # входные изображения 
    images_nobg/                  # результаты 
  models/
    rembg/                        # веса/кеш rembg 
  pyproject.toml                  # зависимости шага 
```

## Кеширование весов (U2NET_HOME)

`rembg` по умолчанию хранит веса в домашней директории пользователя (например, `~/.u2net`).
В этом шаге кеширование перенаправляется в `models/rembg/` через переменную окружения `U2NET_HOME`,
чтобы держать артефакты модели рядом с кодом и упростить воспроизводимость.
