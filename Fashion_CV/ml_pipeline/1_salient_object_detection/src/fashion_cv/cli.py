from __future__ import annotations

import argparse
from pathlib import Path

from fashion_cv.preprocess.remove_bg import RemoveBgOptions, remove_background_batch


def _path(value: str) -> Path:
    return Path(value).expanduser()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fashion-cv")
    sub = parser.add_subparsers(dest="command", required=True)

    remove_bg = sub.add_parser("remove-bg", help="Удалить фон (rembg)")
    remove_bg.add_argument("--input", "-i", type=_path, required=True, help="Путь к файлу или папке")
    remove_bg.add_argument("--output", "-o", type=_path, required=True, help="Путь к файлу или папке")
    remove_bg.add_argument(
        "--background",
        choices=["transparent", "white", "black"],
        default="transparent",
        help="Фон результата",
    )
    remove_bg.add_argument("--model", default="u2net", help="Модель rembg (например: u2net)")
    remove_bg.add_argument(
        "--model-dir",
        type=_path,
        default=None,
        help="Папка с весами rembg (по умолчанию: <project>/models/rembg)",
    )
    remove_bg.add_argument("--recursive", action="store_true", help="Рекурсивно обходить подпапки")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "remove-bg":
        options = RemoveBgOptions(model=args.model, background=args.background, model_dir=args.model_dir)
        outputs = remove_background_batch(
            args.input,
            args.output,
            recursive=bool(args.recursive),
            options=options,
        )
        print(f"Processed: {len(outputs)} image(s)")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
