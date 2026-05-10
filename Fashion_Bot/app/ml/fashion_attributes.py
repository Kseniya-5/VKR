from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import joblib
import numpy as np
from PIL import Image
from skimage.feature import hog
from skimage.transform import resize

ModelType = Literal["RandomForest", "ResNet"]


class FashionModelNotConfigured(RuntimeError):
    """Raised when requested ML artifacts are missing or incompatible."""




def patch_sklearn_tree_compatibility(model: Any) -> Any:
    """
    Делает старые joblib-артефакты RandomForest совместимыми с более новой
    версией scikit-learn.

    Исправляет ошибку вида:
    'DecisionTreeClassifier' object has no attribute 'monotonic_cst'
    """

    def patch_one(obj: Any) -> None:
        if obj is None:
            return

        if not hasattr(obj, "monotonic_cst"):
            try:
                obj.monotonic_cst = None
            except Exception:
                pass

        for estimator in getattr(obj, "estimators_", []) or []:
            patch_one(estimator)

        for attr_name in ("estimator", "estimator_", "base_estimator", "base_estimator_"):
            nested = getattr(obj, attr_name, None)
            if nested is not None:
                patch_one(nested)

    patch_one(model)
    return model


class RandomForestFashionPredictor:
    """
    Runtime for artifacts from Fashion_CV/ml_pipeline/3_attribute_extraction/saved_models/RandomForest.

    Expected files:
      config.joblib
      item.joblib, color.joblib, style.joblib, season.joblib
      item_mlb.joblib, color_mlb.joblib, style_mlb.joblib, season_mlb.joblib
    """

    heads = ("item", "color", "style", "season")

    def __init__(self, models_dir: str | os.PathLike[str]):
        self.models_dir = _normalize_model_dir(Path(models_dir), "RandomForest")

        config_path = self.models_dir / "config.joblib"
        if not config_path.exists():
            raise FashionModelNotConfigured(f"Не найден config.joblib: {config_path}")

        self.config = joblib.load(config_path)
        self.models: dict[str, Any] = {}
        self.mlbs: dict[str, Any] = {}

        missing: list[str] = []
        for head in self.heads:
            model_path = self.models_dir / f"{head}.joblib"
            mlb_path = self.models_dir / f"{head}_mlb.joblib"
            if not model_path.exists():
                missing.append(str(model_path))
                continue
            if not mlb_path.exists():
                missing.append(str(mlb_path))
                continue
            self.models[head] = patch_sklearn_tree_compatibility(joblib.load(model_path))
            self.mlbs[head] = joblib.load(mlb_path)

        if missing:
            raise FashionModelNotConfigured(
                "Не найдены артефакты RandomForest:\n" + "\n".join(missing)
            )

    def predict(self, image_path: str | os.PathLike[str], threshold: float = 0.5) -> dict[str, dict[str, Any]]:
        image = load_image(Path(image_path))
        features = extract_features(image, self.config).reshape(1, -1)

        results: dict[str, dict[str, Any]] = {}
        for head in self.heads:
            clf = self.models[head]
            mlb = self.mlbs[head]

            if hasattr(clf, "predict_proba"):
                probas = clf.predict_proba(features)
                positive_probas = np.array([p[:, 1][0] for p in probas])
                binary_pred = (positive_probas >= threshold).astype(int).reshape(1, -1)
                probability_map = {
                    str(cls): float(prob)
                    for cls, prob in zip(mlb.classes_, positive_probas)
                    if float(prob) >= threshold
                }
            else:
                binary_pred = clf.predict(features)
                probability_map = {}

            labels = list(mlb.inverse_transform(binary_pred)[0])
            results[head] = {
                "labels": [str(label) for label in labels],
                "probabilities": dict(
                    sorted(probability_map.items(), key=lambda item: item[1], reverse=True)
                ),
            }

        return results


class ResNetFashionPredictor:
    """
    Runtime for artifacts from Fashion_CV/ml_pipeline/3_attribute_extraction/saved_models/ResNet.

    Expected files:
      model.pt
      item_mlb.json, color_mlb.json, style_mlb.json, season_mlb.json
    """

    heads = ("item", "color", "style", "season")

    def __init__(self, models_dir: str | os.PathLike[str]):
        # Lazy imports: RandomForest can work even if torch is not installed yet.
        try:
            import torch
            import torch.nn as nn
            from torchvision import models, transforms
        except Exception as exc:  # pragma: no cover - depends on optional heavy deps
            raise FashionModelNotConfigured(
                "Для ResNet нужны зависимости torch и torchvision. "
                "Установите их или выберите RandomForest."
            ) from exc

        self.torch = torch
        self.transforms = transforms
        self.models_dir = _normalize_model_dir(Path(models_dir), "ResNet")

        model_path = self.models_dir / "model.pt"
        if not model_path.exists():
            raise FashionModelNotConfigured(f"Не найден model.pt: {model_path}")

        self.classes: dict[str, list[str]] = {}
        missing: list[str] = []
        for head in self.heads:
            path = self.models_dir / f"{head}_mlb.json"
            if not path.exists():
                missing.append(str(path))
                continue
            with open(path, "r", encoding="utf-8") as f:
                self.classes[head] = [str(x) for x in json.load(f)]

        if missing:
            raise FashionModelNotConfigured(
                "Не найдены JSON-бинаризаторы ResNet:\n" + "\n".join(missing)
            )

        head_sizes = {head: len(values) for head, values in self.classes.items()}

        class MultilabelResNet(nn.Module):
            def __init__(self, sizes: dict[str, int]):
                super().__init__()
                backbone = models.resnet50(weights=None)
                in_features = backbone.fc.in_features
                self.backbone = nn.Sequential(*list(backbone.children())[:-1])
                self.heads = nn.ModuleDict({
                    head_name: nn.Linear(in_features, size)
                    for head_name, size in sizes.items()
                })

            def forward(self, x):
                features = self.backbone(x)
                features = features.flatten(1)
                return {head_name: head(features) for head_name, head in self.heads.items()}

        self.device = "cpu"
        self.model = MultilabelResNet(head_sizes).to(self.device)
        state_dict = torch.load(model_path, map_location=self.device)
        self.model.load_state_dict(state_dict, strict=False)
        self.model.eval()

        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225],
            ),
        ])

    def predict(self, image_path: str | os.PathLike[str], threshold: float = 0.5) -> dict[str, dict[str, Any]]:
        with Image.open(image_path) as img:
            image = img.convert("RGB")
            tensor = self.transform(image).unsqueeze(0).to(self.device)

        with self.torch.no_grad():
            logits_dict = self.model(tensor)

        result: dict[str, dict[str, Any]] = {}
        for head, logits in logits_dict.items():
            probs = self.torch.sigmoid(logits).cpu().numpy()[0]
            labels: list[str] = []
            prob_map: dict[str, float] = {}
            for cls, prob in zip(self.classes[head], probs):
                value = float(prob)
                if value >= threshold:
                    labels.append(cls)
                    prob_map[cls] = value
            result[head] = {
                "labels": labels,
                "probabilities": dict(sorted(prob_map.items(), key=lambda item: item[1], reverse=True)),
            }
        return result


def _normalize_model_dir(path: Path, model_name: str) -> Path:
    if path.name == model_name:
        candidate = path
    else:
        candidate = path / model_name
    if not candidate.exists():
        raise FashionModelNotConfigured(f"Папка модели {model_name} не найдена: {candidate}")
    return candidate


def load_image(path: Path) -> np.ndarray:
    if not path.exists():
        raise FileNotFoundError(f"Файл фото не найден: {path}")
    with Image.open(path) as img:
        rgb = img.convert("RGB")
        return np.array(rgb, dtype=np.uint8)


def extract_hog_features(image: np.ndarray, config: dict[str, Any]) -> np.ndarray:
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


def extract_color_histogram(image: np.ndarray, config: dict[str, Any]) -> np.ndarray:
    if image.dtype != np.uint8:
        image = (image * 255).astype(np.uint8)

    histograms = []
    for channel in range(3):
        hist, _ = np.histogram(
            image[:, :, channel],
            bins=config["COLOR_HIST_BINS"],
            range=(0, 256),
        )
        hist = hist / (hist.sum() + 1e-6)
        histograms.append(hist)
    return np.concatenate(histograms)


def extract_features(image: np.ndarray, config: dict[str, Any]) -> np.ndarray:
    return np.concatenate([
        extract_hog_features(image, config),
        extract_color_histogram(image, config),
    ])


def simplify_predictions(raw: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    return {head: list(data.get("labels") or []) for head, data in raw.items()}


@lru_cache(maxsize=4)
def get_predictor(models_root: str, model_type: str) -> RandomForestFashionPredictor | ResNetFashionPredictor:
    normalized = _normalize_model_type(model_type)
    if normalized == "ResNet":
        return ResNetFashionPredictor(models_root)
    return RandomForestFashionPredictor(models_root)


def _normalize_model_type(model_type: str) -> ModelType:
    value = (model_type or "RandomForest").strip().lower()
    if value in {"resnet", "resnet50", "rn"}:
        return "ResNet"
    return "RandomForest"


def predict_attributes(
    image_path: str | os.PathLike[str],
    *,
    models_root: str,
    model_type: str = "RandomForest",
    threshold: float = 0.5,
) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]], str]:
    normalized = _normalize_model_type(model_type)
    predictor = get_predictor(models_root, normalized)
    raw = predictor.predict(image_path, threshold=threshold)
    return simplify_predictions(raw), raw, normalized
