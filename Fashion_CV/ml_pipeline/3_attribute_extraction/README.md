# Attribute Extraction

Модуль отвечает за извлечение атрибутов одежды по изображению. На выходе модели предсказывают четыре группы признаков:

- `item` / `item_type` - тип вещи;
- `color` - цветовые признаки;
- `style` - стиль;
- `season` - сезонность.

Результаты этого этапа используются дальше в Telegram-боте и рекомендательной логике: после загрузки фотографии бот должен сохранить изображение, отправить его на обработку в Celery worker, получить предсказанные атрибуты и записать их в таблицу `user_photos`.

## Актуальные модели

В этой папке есть две рабочие модели:

```text
saved_models/
├── ResNet50V1/
│   ├── model.pt
│   ├── item_mlb.json
│   ├── color_mlb.json
│   ├── style_mlb.json
│   ├── season_mlb.json
│   └── metrics.json
└── RandoForest/
    ├── item.joblib
    ├── color.joblib
    ├── style.joblib
    └── season.joblib
```

`ResNet50V1` является основной нейросетевой моделью. Она обучена как multi-label classifier с несколькими головами: отдельно для `item`, `color`, `style` и `season`.

`RandoForest` - независимый набор RandomForest-моделей, сохранённых отдельно для каждой группы атрибутов. Название директории сейчас именно `RandoForest`, это важно учитывать в путях.

В интеграции эти модели лучше использовать как два самостоятельных источника предсказаний:

- `ResNet50V1` - основной источник для заполнения текущих полей `user_photos`;
- `RandoForest` - отдельный источник для сравнения, анализа и дополнительной проверки.

Их результаты не нужно принудительно объединять в один ансамблевый ответ. Надёжнее сохранить оба предсказания и явно указать, какая модель что вернула.

Файл `resnet/resnet18_training.ipynb` не используется как актуальная модель. Это экспериментальный ноутбук, его не нужно брать за основу для интеграции.

## Обучающие ноутбуки

Актуальные ноутбуки:

```text
resnet/train_resnet.ipynb
RandomForest/train_ensample.ipynb
```

`resnet/train_resnet.ipynb` содержит:

- подготовку multi-label разметки;
- архитектуру `MultilabelResNet` на базе `ResNet50`;
- обучение модели;
- сохранение весов в `model.pt`;
- сохранение списков классов в `{head}_mlb.json`.

`RandomForest/train_ensample.ipynb` содержит:

- извлечение HOG-признаков;
- извлечение цветовой гистограммы;
- обучение отдельных RandomForest-классификаторов;
- сохранение моделей в `.joblib`.

## Метаданные классов

Файлы:

```text
ResNet50V1/item_mlb.json
ResNet50V1/color_mlb.json
ResNet50V1/style_mlb.json
ResNet50V1/season_mlb.json
```

хранят порядок классов для каждой головы модели. Они нужны, чтобы преобразовать выходной вектор модели в человекочитаемые лейблы.

Пример:

```text
output[0] -> первый класс из *_mlb.json
output[1] -> второй класс из *_mlb.json
...
```

Текущие классы:

```text
item: accessory, ankle boot, bag, beanie, belt, boot, dress, glove, hat, jacket,
      jean, jewelry, jogger, leather jacket, legging, pant, scarf, shirt dress,
      shoe, sneaker, sock, sweater, trouser

color: black, blue, brown, dark, grey, grid, heather, neon, plaid, silver,
       wash, white, with, yellow

style: athleisure, bohemian, boho, boho chic, casual, edgy, grunge,
       minimalist, outdoor, street style, streetwear

season: all - season, fall, winter
```

Эти JSON-файлы можно использовать и для RandomForest только в том случае, если RandomForest обучался на тех же классах и в том же порядке. Для более надёжной интеграции желательно положить копии этих файлов рядом с `.joblib`:

```text
saved_models/RandoForest/item_mlb.json
saved_models/RandoForest/color_mlb.json
saved_models/RandoForest/style_mlb.json
saved_models/RandoForest/season_mlb.json
```

Так у каждой модели будет полный набор собственных артефактов: веса и метаданные классов.

## Метрики ResNet50V1

Основные значения из `ResNet50V1/metrics.json`:

| Голова | Exact match | Precision micro | Recall micro | F1 micro |
| --- | ---: | ---: | ---: | ---: |
| `item` | 0.104 | 0.772 | 0.557 | 0.647 |
| `color` | 0.739 | 0.981 | 0.962 | 0.971 |
| `style` | 0.516 | 0.841 | 0.886 | 0.863 |
| `season` | 0.948 | 0.982 | 1.000 | 0.991 |

По этим метрикам видно, что наиболее уверенно модель работает с `season`, `color` и `style`. Для `item` задача сложнее, поэтому при интеграции полезно сохранять не только итоговый лейбл, но и полный список вероятностей или top-k кандидатов.

## Рекомендуемая интеграция с Telegram-ботом

В `Fashion_Bot` уже есть подходящая инфраструктура:

- Telegram-бот на `aiogram`;
- Celery worker;
- Redis;
- PostgreSQL;
- таблица `user_photos` с полями `item_type`, `color`, `season`, `style`, `tags`, `processing_status`.

Рекомендуемый поток обработки:

1. Пользователь нажимает кнопку `Загрузить фото`.
2. Бот принимает следующее фото и скачивает его в `/app/data/photos`.
3. В таблицу `user_photos` добавляется запись со статусом `uploaded`.
4. Бот ставит Celery-задачу `classify_photo_task(photo_id, image_path)`.
5. Worker загружает модели и выполняет два независимых инференса: `ResNet50V1` и `RandoForest`.
6. Worker обновляет запись в `user_photos`. В основные поля записывается результат основной модели `ResNet50V1`, а полный ответ обеих моделей сохраняется в `tags`:

```sql
UPDATE user_photos
SET processing_status = 'ready',
    item_type = :item_type,
    color = :color,
    season = :season,
    style = :style,
    tags = :model_predictions_json
WHERE id = :photo_id;
```

Если инференс завершился ошибкой, статус должен стать `failed`, а текст ошибки можно сохранить в `photo_processing_jobs.error_message`.

## Где должен жить inference-код

Для интеграции с ботом лучше не импортировать код напрямую из ноутбуков. Нужно вынести минимальный inference-слой в обычные Python-модули внутри `Fashion_Bot`:

```text
Fashion_Bot/app/ml/
├── __init__.py
├── resnet50_inference.py
├── random_forest_inference.py
└── attribute_classifier.py
```

`resnet50_inference.py`:

- описывает класс `MultilabelResNet`;
- загружает `model.pt`;
- читает `{head}_mlb.json`;
- применяет resize до `224x224`;
- применяет ImageNet-нормализацию;
- возвращает вероятности и итоговые лейблы.

`random_forest_inference.py`:

- загружает `.joblib` для `item`, `color`, `style`, `season`;
- повторяет feature extraction из ноутбука: HOG + цветовая гистограмма;
- возвращает предсказанные лейблы.

`attribute_classifier.py`:

- запускает `ResNet50V1` и `RandoForest` как две независимые модели;
- возвращает основной результат `ResNet50V1` для текущих полей БД;
- сохраняет полный ответ обеих моделей в `tags`;
- не смешивает предсказания моделей без отдельного правила выбора.

Минимальный формат результата:

```python
{
    "item_type": "jacket",
    "color": "black",
    "season": "winter",
    "style": "streetwear",
    "model_predictions": {
        "resnet50v1": {
            "item": ["jacket"],
            "color": ["black"],
            "season": ["winter"],
            "style": ["streetwear"]
        },
        "random_forest": {
            "item": ["jacket"],
            "color": ["black"],
            "season": ["winter"],
            "style": ["casual"]
        }
    }
}
```

В этом формате верхние поля (`item_type`, `color`, `season`, `style`) - это значения, которые удобно сразу записывать в `user_photos`. Поле `model_predictions` хранит оба независимых ответа для последующего анализа, отладки или отображения в интерфейсе.

Если позже понадобится выбирать лучший ответ между моделями, это лучше делать отдельным слоем правил, например:

- брать `ResNet50V1` как основной источник;
- показывать предупреждение, если `RandoForest` сильно расходится с `ResNet50V1`;
- использовать `RandoForest` только как fallback, если ResNet50V1 не смогла вернуть уверенный результат.

На текущем этапе оптимальная схема - не смешивать результаты, а сохранять их рядом.

## Подключение моделей в Docker Compose

Сейчас `Fashion_Bot/Dockerfile` копирует только код бота. Директория `Fashion_CV/ml_pipeline/3_attribute_extraction/saved_models` внутрь контейнера не попадает автоматически.

Для локального запуска через `docker-compose` модели можно смонтировать как read-only volume в сервис `worker`:

```yaml
worker:
  volumes:
    - ./data:/app/data
    - static-data:/app/static
    - ../Fashion_CV/ml_pipeline/3_attribute_extraction/saved_models:/app/models:ro
```

Если инференс будет выполняться только в Celery worker, боту достаточно иметь доступ к `/app/data`, а модели нужны именно worker-контейнеру.

Для Kubernetes лучше использовать отдельный volume с моделями или отдельный Docker image, в который веса будут скопированы при сборке.

## Зависимости для инференса

В `Fashion_Bot/pyproject.toml` нужно добавить ML-зависимости:

```toml
"torch",
"torchvision",
"pillow",
"numpy",
"scikit-learn",
"scikit-image",
"joblib",
```

Если RandomForest временно не используется, для первого этапа достаточно подключить только ResNet50V1:

```toml
"torch",
"torchvision",
"pillow",
"numpy",
```

## Рекомендуемый порядок внедрения

1. Подключить только `ResNet50V1` и проверить инференс на одном локальном изображении.
2. Добавить Celery-задачу классификации фото.
3. Добавить обработчик входящих фотографий в Telegram-бот.
4. Записывать результат в `user_photos`.
5. Добавить просмотр загруженных фото и их атрибутов.
6. Подключить `RandoForest` как вторую независимую модель.
7. Сохранять полный ответ обеих моделей в поле `tags`.

Такой порядок снижает риск: сначала появляется рабочий end-to-end сценарий, а потом можно сравнивать качество двух моделей на одинаковых пользовательских фотографиях.
