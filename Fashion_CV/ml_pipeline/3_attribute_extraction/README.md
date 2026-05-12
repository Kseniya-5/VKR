# 3_attribute_extraction

**Автор:** Герилович Илья и Балицкая Ксения

Модуль отвечает за определение атрибутов одежды по изображению. На выходе модели
предсказывают четыре группы признаков:

- `item` / `item_type` - тип вещи;
- `color` - цветовые признаки;
- `style` - стиль;
- `season` - сезонность.

Эти атрибуты используются дальше в Telegram-боте и рекомендательной системе: после загрузки
фотографии бот может определить характеристики вещи, сохранить их в `user_photos`, а затем
передать в графовый рекомендатель из шага `4_fashion_ontology_recsys`.

## Роль в ML-пайплайне

Этот шаг идет после предобработки изображения:

1. Изображение очищается от фона на этапе `1_salient_object_detection`.
2. Модель атрибутов получает изображение вещи.
3. Для каждой группы признаков возвращается один или несколько лейблов.
4. Предсказания сохраняются в БД или передаются в рекомендательную систему.

Минимальный результат инференса:

```python
{
    "item_type": "jacket",
    "color": "black",
    "season": "winter",
    "style": "streetwear"
}
```

Для отладки и сравнения моделей лучше сохранять также полный ответ с вероятностями или
списком лейблов по каждой голове.

## Структура директории

```text
3_attribute_extraction/
├── README.md
├── resnet/
│   ├── train_resnet.ipynb          # актуальное обучение ResNet
│   └── resnet18_training.ipynb     # экспериментальный ноутбук
├── RandomForest/
│   └── train_ensample.ipynb        # обучение RandomForest-моделей
└── saved_models/
    ├── ResNet/
    │   ├── model.pt
    │   ├── item_mlb.json
    │   ├── color_mlb.json
    │   ├── style_mlb.json
    │   ├── season_mlb.json
    │   ├── metrics.json
    │   ├── val_metrics.json
    │   └── test_metrics.json
    └── RandomForest/
        ├── config.joblib
        ├── item.joblib
        ├── color.joblib
        ├── style.joblib
        ├── season.joblib
        ├── item_mlb.joblib
        ├── color_mlb.joblib
        ├── style_mlb.joblib
        └── season_mlb.joblib
```

## Актуальные модели

В папке сохранены два варианта моделей.

### ResNet

`saved_models/ResNet` содержит нейросетевую multi-label модель на базе ResNet. Она использует
общий backbone и отдельные выходные головы для:

- `item`;
- `color`;
- `style`;
- `season`.

Основные артефакты:

- `model.pt` - веса модели;
- `*_mlb.json` - порядок классов для каждой головы;
- `metrics.json`, `val_metrics.json`, `test_metrics.json` - сохраненные метрики.

JSON-файлы с классами обязательны для инференса: без них нельзя корректно сопоставить индекс
выходного нейрона с текстовым лейблом.

### RandomForest

`saved_models/RandomForest` содержит четыре независимые RandomForest-модели:

- `item.joblib`;
- `color.joblib`;
- `style.joblib`;
- `season.joblib`.

Для инференса также нужны:

- `config.joblib` - параметры извлечения признаков;
- `*_mlb.joblib` - бинаризаторы классов.

RandomForest использует признаки HOG и цветовые гистограммы. Этот вариант удобно применять
как дополнительный baseline или независимый источник предсказаний для сравнения с ResNet.

## Обучающие ноутбуки

Актуальные ноутбуки:

```text
resnet/train_resnet.ipynb
RandomForest/train_ensample.ipynb
```

`resnet/train_resnet.ipynb` отвечает за:

- подготовку multi-label разметки;
- описание архитектуры ResNet-модели;
- обучение по четырем группам атрибутов;
- сохранение `model.pt`;
- сохранение классов в `item_mlb.json`, `color_mlb.json`, `style_mlb.json`, `season_mlb.json`.

`RandomForest/train_ensample.ipynb` отвечает за:

- извлечение HOG-признаков;
- построение цветовых гистограмм;
- обучение отдельных RandomForest-классификаторов;
- сохранение `.joblib`-моделей и бинаризаторов.

`resnet/resnet18_training.ipynb` является экспериментальным ноутбуком. Для текущей интеграции
лучше ориентироваться на `train_resnet.ipynb` и артефакты из `saved_models/ResNet`.

## Метаданные классов

Текущие классы ResNet:

```text
item:
  accessory, ankle boot, bag, beanie, belt, boot, dress, glove, hat, jacket,
  jean, jewelry, jogger, leather jacket, legging, pant, scarf, shirt dress,
  shoe, sneaker, sock, sweater, trouser

color:
  black, blue, brown, dark, grey, grid, heather, neon, plaid, silver,
  wash, white, with, yellow

style:
  athleisure, bohemian, boho, boho chic, casual, edgy, grunge,
  minimalist, outdoor, street style, streetwear

season:
  all - season, fall, winter
```

Порядок классов важен. Например:

```text
output[0] -> первый класс из *_mlb.json
output[1] -> второй класс из *_mlb.json
...
```

Для RandomForest порядок классов хранится в `*_mlb.joblib`. Не стоит автоматически заменять
эти файлы JSON-файлами от ResNet, если нет уверенности, что модели обучались на одинаковом
наборе классов в одинаковом порядке.

## Метрики

В `saved_models/ResNet` сейчас лежат несколько файлов с метриками:

- `metrics.json`;
- `val_metrics.json`;
- `test_metrics.json`.

По `test_metrics.json` значения `f1_micro` такие:

| Голова | Exact match | Precision micro | Recall micro | F1 micro |
| --- | ---: | ---: | ---: | ---: |
| `item` | 0.001 | 0.265 | 0.552 | 0.358 |
| `color` | 0.013 | 0.763 | 0.722 | 0.742 |
| `style` | 0.095 | 0.519 | 0.790 | 0.626 |
| `season` | 0.882 | 0.984 | 0.971 | 0.977 |

По этим значениям видно, что лучше всего модель определяет `season`, затем `color` и `style`.
Для `item` задача самая сложная, поэтому при интеграции полезно сохранять не только один
итоговый лейбл, но и top-k кандидатов или вероятности.

`metrics.json` содержит отдельный блок `RandomForest` с метриками baseline-модели. Его можно
использовать для сравнения с ResNet, но при финальном отчете важно явно указывать, из какого
файла и для какой модели взяты значения.

## Формат результата для интеграции

Рекомендуемый формат ответа:

```python
{
    "item_type": "jacket",
    "color": "black",
    "season": "winter",
    "style": "streetwear",
    "model_predictions": {
        "resnet": {
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

Верхние поля удобно сразу записывать в таблицу `user_photos`. Поле `model_predictions` лучше
сохранять в `tags` или в отдельной JSON-колонке, чтобы позже анализировать качество моделей.

## Интеграция с Telegram-ботом

В `Fashion_Bot` этот шаг должен работать как inference-сервис:

1. Бот получает фотографию пользователя.
2. Файл сохраняется в `/app/data/photos`.
3. В `user_photos` создается запись со статусом `uploaded` или `processing`.
4. Celery worker запускает задачу классификации.
5. Worker загружает модель и получает атрибуты.
6. Результат записывается в `user_photos`.
7. При необходимости атрибуты передаются в `4_fashion_ontology_recsys` для рекомендаций.

Пример обновления записи:

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

Если инференс завершился ошибкой, статус должен стать `failed`, а текст ошибки можно сохранить
в таблицу задач обработки или в диагностическое поле.

## Где должен жить inference-код

Ноутбуки не стоит импортировать напрямую в bot runtime. Для интеграции лучше вынести минимальный
inference-слой в обычные Python-модули, например:

```text
Fashion_Bot/app/ml/
├── __init__.py
├── resnet_inference.py
├── random_forest_inference.py
└── attribute_classifier.py
```

`resnet_inference.py`:

- описывает модель;
- загружает `model.pt`;
- читает `*_mlb.json`;
- применяет resize до `224x224`;
- применяет ImageNet-нормализацию;
- возвращает лейблы и вероятности.

`random_forest_inference.py`:

- загружает `.joblib`-модели;
- читает `config.joblib` и `*_mlb.joblib`;
- повторяет feature extraction из ноутбука;
- возвращает предсказанные лейблы.

`attribute_classifier.py`:

- выбирает основную модель для полей БД;
- при необходимости запускает вторую модель для сравнения;
- приводит результат к единому формату;
- не смешивает предсказания моделей без отдельного правила выбора.

## Подключение моделей в Docker Compose

Директория `Fashion_CV/ml_pipeline/3_attribute_extraction/saved_models` не попадет в контейнер
бота автоматически, если ее явно не скопировать или не смонтировать.

Для локального запуска через `docker-compose` модели можно смонтировать в worker read-only:

```yaml
worker:
  volumes:
    - ./data:/app/data
    - ../Fashion_CV/ml_pipeline/3_attribute_extraction/saved_models:/app/models:ro
```

Если инференс выполняется только в Celery worker, модели нужны именно worker-контейнеру.
Telegram bot-контейнеру достаточно иметь доступ к общему каталогу с фотографиями и БД.

## Зависимости для инференса

Для ResNet:

```text
torch
torchvision
pillow
numpy
scikit-learn
```

Для RandomForest дополнительно:

```text
scikit-image
joblib
```

Если на первом этапе нужна только ResNet-модель, RandomForest-зависимости можно не добавлять.

## Рекомендуемый порядок внедрения

1. Подключить ResNet-инференс и проверить его на одном локальном изображении.
2. Добавить Celery-задачу классификации фото.
3. Добавить обработчик входящих фотографий в Telegram-бот.
4. Записывать результат в `user_photos`.
5. Передавать атрибуты в графовый рекомендатель.
6. Подключить RandomForest как дополнительный baseline.
7. Сохранять полный ответ обеих моделей для анализа качества.

Такой порядок сначала дает рабочий end-to-end сценарий, а затем позволяет спокойно сравнивать
качество моделей и улучшать правила выбора результата.

## Текущий статус

Модуль содержит обучающие ноутбуки и сохраненные артефакты двух моделей. Для production-интеграции
нужно вынести инференс из ноутбуков в обычные Python-модули, настроить пути к моделям через
конфиг или переменные окружения и явно выбрать основную модель для заполнения полей БД.
