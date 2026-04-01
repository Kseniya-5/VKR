import os
import json
import time
import google.generativeai as genai
from PIL import Image
from pathlib import Path
from tqdm import tqdm

from config import API_KEY

IMAGE_DIR = "data/images"
OUTPUT_FILE = "data/dataset_annotations.json"

Path(IMAGE_DIR).mkdir(parents=True, exist_ok=True)
Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)


genai.configure(api_key=API_KEY)


PROMPT = """
Act as an expert fashion stylist and computer vision analyst. Analyze the provided image of the clothing item.
Your task is to extract detailed attributes of the main clothing item visible in the photo and return them in a strict JSON format.

Please use the following specific guidelines for filling out the fields. All values in the JSON must be in English:
1. item_type: The specific category (e.g., dress, blouse, trousers, skirt, blazer, coat, t-shirt).
2. demographic: Who is this for? (e.g., women, men, children, unisex).
3. color: The main color and specific shade (e.g., navy blue, beige, crimson red).
4. silhouette: The overall shape (e.g., straight, semi-fitted, fitted, A-line/trapeze, oversize).
5. design_features: Specific construction details or cut (e.g., V-neck, double-breasted, high-waisted, asymmetrical hem).
6. length: Length relative to the body (e.g., mini, midi, maxi, knee-length, cropped, full-length).
7. volume: The fit volume (e.g., tight, regular/moderate, loose/oversized).
8. functional_elements: List as an array (e.g., buttons, zippers, pockets, hood, drawstrings).
9. decorative_elements: List as an array (e.g., visible seams, embroidery, ruffles, pleats, prints, piping).
10. accessories: List as an array (e.g., belt, collar, cuffs, tie).
11. season: Best season for wear (e.g., winter, summer, demi-season/transition, all-season).
12. purpose: The primary occasion (e.g., casual, business, evening, sportswear, loungewear).
13. style: The fashion style (e.g., classic, casual, sporty, boho, minimalist, street style).
14. usage_conditions: Where it should be worn (e.g., office, vacation, gym, party, outdoor).

If a specific attribute is not visible or applicable, use null.
"""
def clean_junk_files(directory):
    """
    Рекурсивно удаляет системный мусор (например, файлы :Zone.Identifier)
    """
    print(f"Очистка мусорных файлов в {directory}...")
    count = 0
    for path in Path(directory).rglob("*:Zone.Identifier"):
        try:
            path.unlink()
            count += 1
        except Exception as e:
            print(f"Не удалось удалить {path}: {e}")
    print(f"Удалено мусорных файлов: {count}")

def analyze_image(image_path, model):
    try:
        img = Image.open(image_path)
        response = model.generate_content([PROMPT, img])
        
        return json.loads(response.text)
    except Exception as e:
        print(f"Ошибка при обработке {image_path}: {e}")
        return None

def main():
    clean_junk_files(IMAGE_DIR)
    
    model = genai.GenerativeModel(
        "gemini-1.5-flash",
        generation_config={"response_mime_type": "application/json"}
    )
    
    image_paths = list(Path(IMAGE_DIR).rglob("*.[jJ][pP][gG]")) + list(Path(IMAGE_DIR).rglob("*.[pP][nN][gG]"))
    
    print(f"Найдено картинок: {len(image_paths)}")
    
    dataset = {}
    
    # Загружаем существующий прогресс, если скрипт прервался
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            dataset = json.load(f)
            print(f"Возобновляем работу. Уже обработано: {len(dataset)}")

    for img_path in tqdm(image_paths):
        relative_path = str(img_path.relative_to(IMAGE_DIR))
        
        # Пропускаем, если уже обработали
        if relative_path in dataset:
            continue
            
        result = analyze_image(img_path, model)
        
        if result:
            dataset[relative_path] = result
            
            # Сохраняем прогресс
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(dataset, f, indent=4, ensure_ascii=False)
        
        # Пауза для обхода лимитов
        time.sleep(4)

    print("Обработка завершена!")

if __name__ == "__main__":
    main()