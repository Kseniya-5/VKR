# 4_fashion_ontology_recsys - графовая рекомендательная система

**Автор:** Герилович Илья и Балицкая Ксения

Модуль отвечает за построение простой ontology-based рекомендательной системы для одежды.
Он связывает результаты извлечения атрибутов с графовой базой Neo4j: вещи из датасета
загружаются в граф, а для новой фотографии система ищет похожие объекты по совпадению
типа вещи, цвета, стиля и сезона.

## Роль в ML-пайплайне

Этот шаг идет после извлечения атрибутов одежды:

1. Пользовательское изображение обрабатывается моделью атрибутов.
2. Модель возвращает признаки:
   - `item` / `item_type` - тип вещи;
   - `color` - цвет;
   - `style` - стиль;
   - `season` - сезон.
3. Эти признаки передаются в Neo4j.
4. Neo4j возвращает top-5 наиболее релевантных вещей из графа.

Текущая реализация предназначена для проверки идеи и локального эксперимента. Для интеграции
с Telegram-ботом этот код лучше вынести в отдельный сервисный слой внутри `Fashion_Bot`.

## Структура директории

```text
4_fashion_ontology_recsys/
├── main.py          # пример end-to-end запуска: загрузка графа, инференс, рекомендации
├── model_utils.py   # загрузка моделей и извлечение признаков для ResNet / RandomForest
└── neo4j_logic.py   # работа с Neo4j: индексы, загрузка данных, поиск рекомендаций
```

## Основные компоненты

### `main.py`

Сценарий демонстрирует полный поток:

- подключается к Neo4j;
- читает JSON с аннотациями датасета;
- загружает аннотации в граф;
- получает предсказания для тестового изображения;
- ищет рекомендации в Neo4j;
- печатает top-5 результатов.

В конце файла выбран запуск через RandomForest:

```python
main(type_model="RandomForest")
```

Для проверки ResNet можно заменить тип модели на:

```python
main(type_model="ResNet")
```

### `model_utils.py`

Содержит inference-логику для двух вариантов моделей:

- `MultilabelResNet` - multi-label ResNet50 с отдельными головами для `item`, `color`, `style`, `season`;
- `FashionPredictor` - RandomForest-инференс на HOG-признаках и цветовых гистограммах.

RandomForest ожидает следующие артефакты:

```text
MODEL_DIR/
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

ResNet ожидает:

```text
MODEL_DIR/
├── model.pt
├── item_mlb.json
├── color_mlb.json
├── style_mlb.json
└── season_mlb.json
```

### `neo4j_logic.py`

Содержит класс `Neo4jRecommender`, который:

- создает constraint для `Item.id`;
- создает индексы для `Category.name` и `Color.name`;
- загружает аннотации в Neo4j батчами;
- строит связи между вещами и атрибутами;
- возвращает top-5 рекомендаций.

В графе используются узлы:

```text
(:Item)
(:Category)
(:Color)
(:Season)
(:Style)
```

И связи:

```text
(:Item)-[:HAS_CATEGORY]->(:Category)
(:Item)-[:HAS_COLOR]->(:Color)
(:Item)-[:HAS_SEASON]->(:Season)
(:Item)-[:HAS_STYLE]->(:Style)
```

## Формат входных аннотаций

`main.py` ожидает JSON-файл со структурой:

```json
{
  "images/example.jpg": {
    "0": {
      "item_type": "jacket",
      "color": "black",
      "season": "winter",
      "style": "streetwear"
    },
    "1": {
      "item_type": "sneaker",
      "color": "white",
      "season": "all-season",
      "style": "casual"
    }
  }
}
```

Для каждого объекта создается отдельный `Item` с id формата:

```text
<image_path>#<object_id>
```

Например:

```text
images/example.jpg#0
```

## Логика ранжирования рекомендаций

Рекомендации считаются по взвешенному совпадению атрибутов:

| Атрибут | Вес |
| --- | ---: |
| `item` / категория | 3 |
| `color` | 2 |
| `style` | 2 |
| `season` | 1 |

Максимальный score равен `8`, если совпали все четыре группы признаков.

Пример входа для поиска:

```python
{
    "item": ["jacket"],
    "color": ["black"],
    "season": ["winter"],
    "style": ["streetwear"]
}
```

Пример результата:

```python
[
    {
        "id": "images/example.jpg#0",
        "image": "images/example.jpg",
        "score": 8
    }
]
```

## Быстрый старт

Поднимите Neo4j локально или через Docker:

```bash
docker run --rm \
  --name fashion-neo4j \
  -p 7474:7474 \
  -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:5
```

Установите зависимости в окружение проекта:

```bash
pip install neo4j torch torchvision pillow numpy scikit-learn scikit-image joblib
```

Если используется только графовая часть без инференса моделей, достаточно:

```bash
pip install neo4j
```

## Запуск

Перед запуском проверьте константы в `main.py`:

```python
ANNOTATIONS_FILE = "/opt/clearml_date/test/dataset_annotations.json"
IMAGE_TO_TEST = "/opt/clearml_date/test/test/test.jpg"
MODEL_DIR = "/opt/clearml_date/test/saved_models/RandomForest"
```

Они должны указывать на реальные файлы в вашем окружении.

Также проверьте параметры подключения к Neo4j:

```python
rec = Neo4jRecommender("bolt://neo4j:7687", "neo4j", "password")
```

Для локального запуска вне Docker чаще всего нужен адрес:

```python
rec = Neo4jRecommender("bolt://localhost:7687", "neo4j", "password")
```

Запуск:

```bash
cd Fashion_CV/ml_pipeline/4_fashion_ontology_recsys
python main.py
```

## Интеграция с Telegram-ботом

В production-сценарии не стоит каждый раз загружать весь датасет в Neo4j при обработке фото.
Рекомендуемый поток:

1. Один раз загрузить каталог вещей и их атрибуты в Neo4j.
2. После загрузки пользовательского фото получить атрибуты через модуль `3_attribute_extraction`.
3. Передать предсказания в `Neo4jRecommender.get_recommendations`.
4. Сохранить рекомендации в БД бота или вернуть их пользователю сразу.

Минимальный формат входа для рекомендателя:

```python
predictions = {
    "item": ["jacket"],
    "color": ["black"],
    "season": ["winter"],
    "style": ["streetwear"]
}
```

Если в таблице `user_photos` используются поля `item_type`, `color`, `season`, `style`, то перед
вызовом Neo4j нужно привести `item_type` к ключу `item`.

## Что важно доработать

- Вынести пути, логин и пароль Neo4j из `main.py` в переменные окружения или конфиг.
- Разделить разовую загрузку датасета в граф и online-рекомендации для пользовательских фото.
- Добавить CLI-аргументы для `ANNOTATIONS_FILE`, `IMAGE_TO_TEST`, `MODEL_DIR` и типа модели.
- В `model_utils.py` импортировать `requests`, если нужна загрузка изображений по URL.
- Убедиться, что название директории с RandomForest совпадает с реальными артефактами (`RandomForest` или `RandoForest`).
- Добавить очистку или версионирование графа, чтобы повторная загрузка не смешивала разные версии датасета.

## Текущий статус

Модуль можно использовать как экспериментальный прототип:

- Neo4j хранит вещи и атрибуты в виде графа;
- ResNet или RandomForest извлекают атрибуты для нового изображения;
- рекомендации строятся по понятной weighted-score логике.

Для стабильной интеграции с ботом рекомендуется сначала оформить этот код как сервис:
`load_graph_once`, `predict_attributes`, `get_recommendations_for_photo`.
