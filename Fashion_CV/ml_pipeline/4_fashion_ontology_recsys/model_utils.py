import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image
import json
import os
import numpy as np
import joblib
import numpy as np
from skimage.io import imread
from skimage.transform import resize
from skimage.feature import hog
from sklearn.preprocessing import MultiLabelBinarizer

DEVICE = "cpu"
IMAGE_SIZE = (224, 224)

class FashionPredictor:
    def __init__(self, models_dir: str = "saved_models", artifacts_dir: str = "inference_artifacts"):
        self.models_dir = models_dir
        self.artifacts_dir = artifacts_dir
        
        # Загружаем конфиг с параметрами (IMAGE_SIZE, HOG_PIXELS_PER_CELL и т.д.)
        config_path = os.path.join(artifacts_dir, "config.joblib")
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Не найден файл конфигурации: {config_path}")
        self.config = joblib.load(config_path)
        
        self.heads = ["item", "color", "style", "season"]
        self.model_name = "RandomForest"
        
        # Загружаем модели и бинаризаторы
        self.models = {}
        self.mlbs = {}
        
        for head in self.heads:
            model_path = os.path.join(models_dir, f"{head}.joblib")
            mlb_path = os.path.join(artifacts_dir, f"{head}_mlb.joblib")
            
            if not os.path.exists(model_path) or not os.path.exists(mlb_path):
                raise FileNotFoundError(f"Не найдены артефакты для головы {head}")
            
            self.models[head] = joblib.load(model_path)
            self.mlbs[head] = joblib.load(mlb_path)

    def predict(self, image_path: str, threshold: float = 0.5) -> dict:
        """
        Принимает путь к картинке, возвращает словарь с предсказанными лейблами.
        """
        # Загружаем изображение
        image = load_image(image_path)
        if image is None:
            return {}

        # Извлекаем признаки, передавая config
        features = extract_features(image, self.config).reshape(1, -1)

        results = {}
        for head in self.heads:
            clf = self.models[head]
            mlb = self.mlbs[head]

            # Получаем вероятности
            if hasattr(clf, "predict_proba"):
                probas = clf.predict_proba(features)
                positive_probas = np.array([p[:, 1][0] for p in probas])
                
                # Применяем порог
                binary_pred = (positive_probas >= threshold).astype(int).reshape(1, -1)
                
                # Сохраняем вероятности
                prob_dict = {cls: float(prob) for cls, prob in zip(mlb.classes_, positive_probas) if prob >= threshold}
            else:
                binary_pred = clf.predict(features)
                prob_dict = None

            # Переводим нули и единицы обратно в текст
            predicted_labels = mlb.inverse_transform(binary_pred)[0]
            
            # Формируем вывод
            results[head] = {
                "labels": list(predicted_labels),
                "probabilities": dict(sorted(prob_dict.items(), key=lambda x: x[1], reverse=True)) if prob_dict else None
            }

        return results

class MultilabelResNet(nn.Module):
    def __init__(self, head_sizes: dict[str, int]):
        super().__init__()
        backbone = models.resnet50(weights=None)
        in_features = backbone.fc.in_features
        self.backbone = nn.Sequential(*list(backbone.children())[:-1])
        self.heads = nn.ModuleDict({
            head: nn.Linear(in_features, num_classes)
            for head, num_classes in head_sizes.items()
        })

    def forward(self, x):
        features = self.backbone(x)
        features = features.flatten(1)
        return {
            head: self.heads[head](features)
            for head in self.heads
        }

inference_transforms = transforms.Compose([
    transforms.Resize(IMAGE_SIZE),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

def load_model(save_dir: str = "/home/ubuntu/upload") -> tuple[MultilabelResNet, dict]:
    mlb_dict = {}
    head_sizes = {}
    for filename in os.listdir(save_dir):
        if not filename.endswith("_mlb.json"):
            continue
        head_name = filename.replace("_mlb.json", "")
        path = os.path.join(save_dir, filename)
        with open(path, "r", encoding="utf-8") as f:
            classes = json.load(f)
        mlb = MultiLabelBinarizer()
        mlb.classes_ = np.array(classes)
        mlb_dict[head_name] = mlb
        head_sizes[head_name] = len(classes)
    
    model = MultilabelResNet(head_sizes).to(DEVICE)
    # Загружаем веса, игнорируя несовпадения если они есть (на случай если style_mlb не совпал)
    state_dict = torch.load(os.path.join(save_dir, "model.pt"), map_location=DEVICE)
    model.load_state_dict(state_dict, strict=False)
    model.eval()
    return model, mlb_dict

def predict_single(image_source, model, mlb_dict, threshold=0.5):
    if isinstance(image_source, str):
        image = Image.open(image_source).convert("RGB")
    else:
        image = image_source.convert("RGB")
    tensor = inference_transforms(image).unsqueeze(0).to(DEVICE)
    with torch.no_grad():
        logits_dict = model(tensor)
    result = {}
    for head_name, logits in logits_dict.items():
        probs = torch.sigmoid(logits).cpu().numpy()[0]
        binary = (probs >= threshold).astype(int)
        mlb = mlb_dict[head_name]
        classes = mlb.classes_
        result[head_name] = [cls for cls, flag in zip(classes, binary) if flag]
    return result

def load_image(path: str) -> np.ndarray | None:
    """
    Загружает изображение с диска или по URL.
    Возвращает RGB-массив (H, W, 3) или None при ошибке.
    Всегда возвращает uint8 (0-255) для стабильности гистограмм.
    """
    try:
        # Попытка загрузить с диска
        if os.path.exists(path):
            img = Image.open(path).convert("RGB")
        
        # Попытка загрузить по URL
        elif path.startswith("http"):
            response = requests.get(path, timeout=10)
            response.raise_for_status()
            img = Image.open(requests.utils.io.BytesIO(response.content)).convert("RGB")
        
        else:
            print(f"Файл не найден: {path}")
            return None
            
        return np.array(img, dtype=np.uint8) # ВАЖНО: явно указываем uint8
        
    except Exception as e:
        print(f"Ошибка загрузки {path}: {e}")
        return None


def extract_hog_features(image: np.ndarray, config: dict) -> np.ndarray:
    """
    HOG-признаки по всем трём RGB-каналам.
    Изображение предварительно масштабируется до IMAGE_SIZE.
    """
    img_resized = resize(image, config["IMAGE_SIZE"], anti_aliasing=True)
 
    hog_channels = []
    for channel in range(3):
        features = hog(
            img_resized[:, :, channel],
            pixels_per_cell=config["HOG_PIXELS_PER_CELL"],
            cells_per_block=config["HOG_CELLS_PER_BLOCK"],
            feature_vector=True,
        )
        hog_channels.append(features)
 
    return np.concatenate(hog_channels)
 
 
def extract_color_histogram(image: np.ndarray, config: dict) -> np.ndarray:
    """
    Нормированная гистограмма цветов по каждому RGB-каналу.
    """
    # Защита: если пришло float (от resize или другого загрузчика), конвертим в uint8
    if image.dtype != np.uint8:
        image = (image * 255).astype(np.uint8)

    histograms = []
    for channel in range(3):
        hist, _ = np.histogram(
            image[:, :, channel],
            bins=config["COLOR_HIST_BINS"],
            range=(0, 256),
        )
        hist = hist / (hist.sum() + 1e-6)  # нормализация
        histograms.append(hist)
 
    return np.concatenate(histograms)
 
 
def extract_features(image: np.ndarray, config: dict) -> np.ndarray:
    """Объединяет HOG и цветовую гистограмму в единый вектор признаков."""
    # Передаем config дальше
    hog_features = extract_hog_features(image, config)
    
    # Для цветовой гистограммы передаем оригинальный размер (не resized),
    # так как resize искажает распределение цветов.
    color_features = extract_color_histogram(image, config)
    
    return np.concatenate([hog_features, color_features])

def format_rf_predictions(rf_result: dict) -> dict:
    """
    Приводит результат FashionPredictor к формату, понятному Neo4j
    (оставляем только списки лейблов, убираем вероятности).
    Формат: {"item": ["dress"], "color": ["red", "blue"], ...}
    """
    formatted = {}
    for head_name, data in rf_result.items():
        formatted[head_name] = data.get("labels", [])
    return formatted