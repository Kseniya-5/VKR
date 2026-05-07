import json
from model_utils import load_model, predict_single, format_rf_predictions
from model_utils import FashionPredictor
from neo4j_logic import Neo4jRecommender

# 1. Настройки
ANNOTATIONS_FILE = "/opt/clearml_date/test/dataset_annotations.json"  # Путь к аннотациям
IMAGE_TO_TEST = "/opt/clearml_date/test/test/test.jpg"                  # Изображение для теста
MODEL_DIR = "/opt/clearml_date/test/saved_models/RandomForest"                                 # Папка, где лежат .pt и .json файлы

def main(type_model: str):

    # 1. Подключаемся к Neo4j
    print("Подключение к Neo4j...")
    rec = Neo4jRecommender("bolt://neo4j:7687", "neo4j", "password")

    # 2. Загружаем все аннотации из вашего JSON в граф
    print(f"Загрузка данных из {ANNOTATIONS_FILE} в граф...")
    with open(ANNOTATIONS_FILE, "r", encoding="utf-8") as f:
        full_annotations = json.load(f)
    
    # Загружаем данные (это нужно сделать один раз)
    rec.upload_data(full_annotations)
    print("Данные успешно загружены в Neo4j.")

    # 3. Получаем предсказания для нового изображения
    print(f"Анализ изображения {IMAGE_TO_TEST}...")

    # 4. Загружаем модель и классификаторы
    print("Загрузка модели...")
    if type_model == 'ResNet':
        model, mlb_dict = load_model(MODEL_DIR)

        predictions = predict_single(IMAGE_TO_TEST, model, mlb_dict)
    elif type_model == 'RandomForest':
        predictor = FashionPredictor(models_dir=MODEL_DIR, artifacts_dir=MODEL_DIR)
        result = predictor.predict(IMAGE_TO_TEST, threshold=0.5)
        for head_name, data in result.items():
            print(f"[{head_name.upper()}]")
            if not data["labels"]:
                print("  Ничего не найдено")
            else:
                for label in data["labels"]:
                    prob = data["probabilities"].get(label, "N/A")
                    print(f"  - {label} (вероятность: {prob:.2f})")
        predictions = format_rf_predictions(result)

    print("Предсказания модели:", predictions)

    # 5. Получаем рекомендации из Neo4j
    print("Поиск рекомендаций в графе...")
    recommendations = rec.get_recommendations(predictions)

    # 6. Вывод результатов
    print("\n--- ТОП-5 РЕКОМЕНДАЦИЙ ---")
    if not recommendations:
        print("Рекомендаций не найдено.")
    for i, r in enumerate(recommendations, 1):
        print(f"{i}. ID: {r['id']}")
        print(f"   Балл релевантности: {r['score']}")
        print(f"   Путь к фото: {r['image']}\n")

    rec.close()

if __name__ == "__main__":
    # Тип модели либо ResNet, либо RandomForest
    main(type_model='RandomForest')
