from __future__ import annotations

import io
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

from PIL import Image
from rembg import new_session, remove

ImageExt = Literal[".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"]


@dataclass(frozen=True)
class RemoveBgOptions:
    model: str = "u2net"
    background: Literal["transparent", "white", "black"] = "transparent"
    model_dir: Path | None = None


def _ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _find_project_root(start: Path) -> Path:
    current = start
    for _ in range(10):
        if (current / "pyproject.toml").is_file():
            return current
        if current.parent == current:
            break
        current = current.parent
    return start


def _default_model_dir() -> Path:
    # src/fashion_cv/preprocess/remove_bg.py -> .../<project_root>
    project_root = _find_project_root(Path(__file__).resolve().parent)
    return project_root / "models" / "rembg"


def _configure_model_dir(options: RemoveBgOptions) -> Path:
    model_dir = (options.model_dir or _default_model_dir()).resolve()
    model_dir.mkdir(parents=True, exist_ok=True)

    # rembg (u2net session) по умолчанию хранит веса в ~/.u2net.
    # Чтобы держать всё внутри проекта, направляем кеш через U2NET_HOME.
    if options.model_dir is not None:
        os.environ["U2NET_HOME"] = str(model_dir)
    else:
        os.environ.setdefault("U2NET_HOME", str(model_dir))

    return model_dir


def _coerce_image(output: object) -> Image.Image:
    if isinstance(output, Image.Image):
        return output
    if isinstance(output, (bytes, bytearray, memoryview)):
        return Image.open(io.BytesIO(bytes(output)))
    raise TypeError(f"Unsupported rembg output type: {type(output)!r}")


def remove_background(
    input_path: Path,
    output_path: Path,
    *,
    options: RemoveBgOptions | None = None,
) -> Path:
    options = options or RemoveBgOptions()

    _configure_model_dir(options)
    session = new_session(options.model)
    with Image.open(input_path) as img:
        img = img.convert("RGBA")
        result = _coerce_image(remove(img, session=session)).convert("RGBA")

    if options.background in {"white", "black"}:
        background_rgb = (255, 255, 255, 255) if options.background == "white" else (0, 0, 0, 255)
        bg = Image.new("RGBA", result.size, background_rgb)
        result = Image.alpha_composite(bg, result).convert("RGB")

    _ensure_parent_dir(output_path)
    result.save(output_path)
    return output_path


def _iter_images(root: Path, *, recursive: bool) -> Iterable[Path]:
    if root.is_file():
        yield root
        return

    patterns = ["*"]
    walker = root.rglob if recursive else root.glob
    for pattern in patterns:
        for p in walker(pattern):
            if not p.is_file():
                continue
            if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}:
                yield p


def remove_background_batch(
    input_path: Path,
    output_path: Path,
    *,
    recursive: bool = False,
    options: RemoveBgOptions | None = None,
) -> list[Path]:
    input_path = input_path.resolve()
    output_path = output_path.resolve()
    options = options or RemoveBgOptions()

    outputs: list[Path] = []

    if input_path.is_file():
        out_file = output_path
        if output_path.is_dir():
            out_file = output_path / (input_path.stem + ".png")
        outputs.append(remove_background(input_path, out_file, options=options))
        return outputs

    for img_path in _iter_images(input_path, recursive=recursive):
        rel = img_path.relative_to(input_path)
        # По умолчанию сохраняем как PNG (прозрачность).
        suffix = rel.suffix
        if options.background == "transparent":
            suffix = ".png"
        out_file = (output_path / rel).with_suffix(suffix)
        outputs.append(remove_background(img_path, out_file, options=options))

    return outputs
