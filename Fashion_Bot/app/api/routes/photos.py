from typing import Any
from uuid import uuid4
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File,
    HTTPException,
    status,
    Query,
    Form,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text, bindparam
from PIL import Image

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
except Exception:
    # Optional dependency. JPG/PNG/WEBP still work without it.
    pass

from app.core.deps import get_current_user
from app.db.session import get_db
from app.db.models import User
from app.core.config import settings


router = APIRouter(prefix="/photos", tags=["photos"])

MEDIA_ROOT = Path("/app/media")
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)


class BulkDeletePhotosRequest(BaseModel):
    photo_ids: list[str] = Field(min_length=1, max_length=200)


def _public_photo_url(photo_id: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/api/photos/{photo_id}/file"


def _api_photo_path(photo_id: str) -> str:
    return f"/api/photos/{photo_id}/file"


@router.post("/upload")
async def upload_photo(
    file: UploadFile = File(...),
    telegram_file_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Content-Type у некоторых браузеров/Telegram может быть неточным, поэтому
    # основную проверку делаем через Pillow: если файл не изображение, он не откроется.
    content_type = file.content_type or ""
    if content_type and not (
        content_type.startswith("image/") or content_type == "application/octet-stream"
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Можно загружать только изображения",
        )

    photo_id = uuid4()
    jpeg_rel_path = Path("user_photos") / str(current_user.id) / f"{photo_id}.jpg"
    jpeg_path = MEDIA_ROOT / jpeg_rel_path
    jpeg_path.parent.mkdir(parents=True, exist_ok=True)

    image = None
    try:
        image = Image.open(file.file)
        image.load()
        image = image.convert("RGB")
        image.save(jpeg_path, format="JPEG", quality=90, optimize=True)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось прочитать файл как изображение",
        )
    finally:
        try:
            file.file.close()
        except Exception:
            pass
        if image is not None:
            try:
                image.close()
            except Exception:
                pass

    await db.execute(
        text(
            """
            INSERT INTO user_photos (
                id,
                user_id,
                source,
                original_path,
                processed_path,
                preview_path,
                mime_type,
                file_size,
                telegram_file_id,
                is_active
            )
            VALUES (
                :id,
                :user_id,
                :source,
                :original_path,
                :processed_path,
                :preview_path,
                :mime_type,
                :file_size,
                :telegram_file_id,
                TRUE
            )
            """
        ),
        {
            "id": str(photo_id),
            "user_id": str(current_user.id),
            "source": "telegram" if telegram_file_id else "web",
            "original_path": str(jpeg_rel_path),
            "processed_path": None,
            "preview_path": None,
            "mime_type": "image/jpeg",
            "file_size": jpeg_path.stat().st_size,
            "telegram_file_id": telegram_file_id,
        },
    )
    await db.commit()

    return {
        "message": "Фото загружено",
        "photo_id": str(photo_id),
        "url": _public_photo_url(str(photo_id)),
        "file_path": _api_photo_path(str(photo_id)),
    }


@router.get("")
@router.get("/")
async def list_photos(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    offset = (page - 1) * page_size

    count_result = await db.execute(
        text(
            """
            SELECT COUNT(*) AS total
            FROM user_photos
            WHERE user_id = :user_id
              AND is_active = TRUE
            """
        ),
        {"user_id": str(current_user.id)},
    )
    total = count_result.scalar_one()

    result = await db.execute(
        text(
            """
            SELECT
                id,
                original_path,
                preview_path,
                telegram_file_id,
                created_at
            FROM user_photos
            WHERE user_id = :user_id
              AND is_active = TRUE
            ORDER BY created_at DESC
            LIMIT :limit OFFSET :offset
            """
        ),
        {
            "user_id": str(current_user.id),
            "limit": page_size,
            "offset": offset,
        },
    )
    rows = result.mappings().all()

    items = [
        {
            "id": str(row["id"]),
            "url": _public_photo_url(str(row["id"])),
            "file_path": _api_photo_path(str(row["id"])),
            "telegram_file_id": row["telegram_file_id"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
        }
        for row in rows
    ]

    return {"total": total, "items": items}


@router.delete("/all")
async def delete_all_photos(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await db.execute(
        text(
            """
            UPDATE user_photos
            SET is_active = FALSE,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = :user_id
              AND is_active = TRUE
            """
        ),
        {"user_id": str(current_user.id)},
    )
    await db.commit()

    return {"message": "Все фото удалены"}


@router.post("/bulk-delete")
async def bulk_delete_photos(
    payload: BulkDeletePhotosRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    stmt = text(
        """
        UPDATE user_photos
        SET is_active = FALSE,
            updated_at = CURRENT_TIMESTAMP
        WHERE user_id = :user_id
          AND is_active = TRUE
          AND id::text IN :photo_ids
        RETURNING id
        """
    ).bindparams(bindparam("photo_ids", expanding=True))

    result = await db.execute(
        stmt,
        {
            "user_id": str(current_user.id),
            "photo_ids": payload.photo_ids,
        },
    )
    rows = result.fetchall()
    await db.commit()

    return {
        "message": "Выбранные фото удалены",
        "deleted_count": len(rows),
        "deleted_ids": [str(row[0]) for row in rows],
    }


@router.get("/{photo_id}/file")
async def get_photo_file(
    photo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        text(
            """
            SELECT
                id,
                user_id,
                original_path,
                mime_type,
                is_active
            FROM user_photos
            WHERE id = :photo_id
            LIMIT 1
            """
        ),
        {"photo_id": photo_id},
    )
    row = result.mappings().first()

    if not row or not row["is_active"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found",
        )

    if str(row["user_id"]) != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to access this photo",
        )

    if not row["original_path"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File path is missing",
        )

    file_path = MEDIA_ROOT / row["original_path"]

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found on disk",
        )

    return FileResponse(
        path=file_path,
        media_type=row["mime_type"] or "image/jpeg",
        filename=file_path.name,
    )


@router.delete("/{photo_id}")
async def delete_photo(
    photo_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        text(
            """
            SELECT id, user_id, is_active
            FROM user_photos
            WHERE id = :photo_id
            LIMIT 1
            """
        ),
        {"photo_id": photo_id},
    )
    row = result.mappings().first()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Photo not found",
        )

    if str(row["user_id"]) != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to delete this photo",
        )

    if not row["is_active"]:
        return {"message": "Photo is already deleted"}

    await db.execute(
        text(
            """
            UPDATE user_photos
            SET is_active = FALSE,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :photo_id
            """
        ),
        {"photo_id": photo_id},
    )
    await db.commit()

    return {"message": "Photo deleted successfully"}
