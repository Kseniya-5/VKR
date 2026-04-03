import os
import json
import time
import random
import base64
import requests
import shutil
from pathlib import Path
from tqdm import tqdm
import re

from config import API_KEY
from config import API_URL

IMAGE_DIR = "data/images"
TRAINING_DIR = "data/images_for_training"
OUTPUT_FILE = "data/dataset_annotations.json"
NUM_SAMPLES = 15000

Path(IMAGE_DIR).mkdir(parents=True, exist_ok=True)
Path(TRAINING_DIR).mkdir(parents=True, exist_ok=True)
Path(OUTPUT_FILE).parent.mkdir(parents=True, exist_ok=True)

PROMPT = """
Act as an expert fashion stylist and computer vision analyst. Analyze the provided image.
The image may contain multiple clothing items forming an outfit. Your task is to identify EACH distinct clothing item or prominent accessory worn by the person and describe them.

Return the result as a strict JSON object where EACH KEY is a descriptive name of the item (e.g., "plaid_shirt_dress", "grey_sweater", "neon_beanie"), and its VALUE is a JSON object containing the attributes for that specific item.

For EACH item, provide the following attributes in English (use null if not applicable):
1. item_type: The specific category (e.g., dress, sweater, beanie, trousers).
2. demographic: Who is this for? (e.g., women, men, children, unisex).
3. age_group: The typical age range (e.g., teenagers, young adults 18-35, all ages).
4. color: The main color and pattern if applicable (e.g., black with white grid, heather grey, neon yellow).
5. silhouette: The overall shape (e.g., straight, fitted, oversized).
6. design_features: Specific construction details (e.g., button-down, V-neck, ribbed knit).
7. length: Length relative to the body (e.g., midi, cropped, knee-length, null for hats/accessories).
8. volume: The fit volume (e.g., tight, loose).
9. functional_elements: Array of functional details (e.g., ["buttons", "pockets"]).
10. decorative_elements: Array of decorative details (e.g., ["grid pattern", "chunky knit"]).
11. accessories: Array of accessories attached to or worn directly over this item.
12. season: Best season for wear (e.g., winter, fall, all-season).
13. purpose: The primary occasion (e.g., casual, street style).
14. style: The fashion style (e.g., grunge, casual, minimalist).
15. usage_conditions: Where it should be worn (e.g., outdoor, casual walk).

Output ONLY the JSON object, no markdown formatting or extra text.
Example structure:
{
  "outer_layer": {
    "item_type": "shirt dress",
    ...
  },
  "inner_layer": {
    "item_type": "sweater",
    ...
  }
}
"""

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def analyze_image(image_path, max_retries=3):
    for attempt in range(max_retries):
        try:
            base64_image = encode_image(image_path)
            
            headers = {
                "Authorization": f"Bearer {API_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "llama3.2-vision:latest",
                "temperature": 0.1,
                "messages": [
                    {
                        "role": "user",
                        "content": f"{PROMPT}\n\n[Image Attached]",
                        "images": [f"data:image/jpeg;base64,{base64_image}"] 
                    }
                ]
            }

            response = requests.post(API_URL, headers=headers, json=payload, timeout=120)
            
            if response.status_code != 200:
                print(f"\nОшибка сервера {response.status_code} для {image_path}: {response.text}")
                time.sleep(2)
                continue
                
            response_data = response.json()
            
            if not response_data or "choices" not in response_data or not response_data["choices"]:
                print(f"\nСтранный ответ от сервера. Сервер вернул: {response_data}")
                time.sleep(2)
                continue
                
            content = response_data['choices'][0]['message'].get('content')
            
            if not content:
                print(f"\nСервер вернул пустой текст для {image_path}")
                time.sleep(2)
                continue
            
            # Вытаскиваем JSON из ответа
            start_idx = content.find('{')
            end_idx = content.rfind('}')
            
            if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                json_str = content[start_idx:end_idx+1]
                return json.loads(json_str)
            else:
                print(f"\nМодель вернула текст без JSON: {content[:100]}...")
                time.sleep(2)
                continue
            
        except json.JSONDecodeError as e:
            print(f"\nМодель вернула невалидный JSON. Попытка {attempt+1}/{max_retries}")
            time.sleep(2)
        except Exception as e:
            print(f"\nСетевая ошибка при обработке: {e}. Попытка {attempt+1}/{max_retries}")
            time.sleep(2)
            
    print(f"\nПропущена картинка {image_path} после {max_retries} неудачных попыток.")
    return None

def main():
    all_image_paths = []
    junk_count = 0
    
    print("Сканирование папок и очистка мусора...")
    for root, _, files in os.walk(IMAGE_DIR):
        for file in sorted(files):
            filepath = os.path.join(root, file)
            
            if file.endswith(':Zone.Identifier'):
                try:
                    os.remove(filepath)
                    junk_count += 1
                except:
                    pass
            elif file.lower().endswith(('.jpg')):
                all_image_paths.append(filepath)

    print(f"Удалено мусорных файлов: {junk_count}")
    print(f"Всего найдено картинок в исходной папке: {len(all_image_paths)}")
    
    random.seed(42)
    sample_size = min(NUM_SAMPLES, len(all_image_paths))
    selected_image_paths = random.sample(all_image_paths, sample_size)
    
    print(f"Отобрано для обучения: {len(selected_image_paths)} случайных фотографий.")
    
    print("Копирование файлов в единую папку (images_for_training)...")
    training_image_paths = []
    
    for original_path in tqdm(selected_image_paths, desc="Копирование"):
        rel_path = os.path.relpath(original_path, IMAGE_DIR)
        
        flat_filename = rel_path.replace(os.sep, "_")
        new_path = os.path.join(TRAINING_DIR, flat_filename)
        
        if not os.path.exists(new_path):
            shutil.copy2(original_path, new_path)
            
        training_image_paths.append(new_path)
    
    dataset = {}
    
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
            dataset = json.load(f)
            print(f"Возобновляем работу. Уже обработано и сохранено в JSON: {len(dataset)}")

    images_to_process = []
    for img_path in training_image_paths:
        relative_json_path = os.path.relpath(img_path, "data")
        if relative_json_path not in dataset:
            images_to_process.append(img_path)

    print(f"Осталось обработать: {len(images_to_process)}")
    print(f"Начинаем анализ через {API_URL}...")
    
    if not images_to_process:
        print("Вся выборка уже обработана!")
        return

    for img_path in tqdm(images_to_process, desc="Анализ нейросетью"):
        relative_json_path = os.path.relpath(img_path, "data")
        
        result = analyze_image(img_path)
        
        if result:
            dataset[relative_json_path] = result
            
            with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
                json.dump(dataset, f, indent=4, ensure_ascii=False)
        
        time.sleep(0.5)

    print("Обработка полностью завершена!")

if __name__ == "__main__":
    main()