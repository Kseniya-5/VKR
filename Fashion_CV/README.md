# Fashion_CV (ML-ядро)

Здесь живёт ML-часть проекта и пошаговый пайплайн подготовки данных/фич для CV и рекомендаций.

## Структура

```text
Fashion_CV/
  create_dataset/
  ml_pipeline/
    1_salient_object_detection/
      README.md
    2_dataset_preparation.ipynb
    3_attribute_extraction.ipynb
    4_fashion_ontology_recsys.ipynb
```

## Шаг 1: Salient Object Detection / Background Removal

Папка шага: `Fashion_CV/ml_pipeline/1_salient_object_detection/`

Зачем нужно: привести домашние фотографии к более «датасетному» виду — выделить вещь и убрать фон (прозрачный/белый/чёрный), чтобы дальше было проще делать подготовку датасета и извлечение атрибутов.

Как запускать: см. `Fashion_CV/ml_pipeline/1_salient_object_detection/README.md`.
