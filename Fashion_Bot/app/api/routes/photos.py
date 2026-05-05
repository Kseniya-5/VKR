from typing import Dict, Any
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
    Request,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from PIL import Image
from fastapi import Form
from app.core.deps import get_current_user
from app.db.session import get_db
from app.db.models import User
from app.core.config import settings

router = APIRouter(prefix="/photos", tags=["photos"])

MEDIA_ROOT = Path("/app/media")

@router.post("/upload")
async def upload_photo(
    file: UploadFile = File(...),
    telegram_file_id: str = Form(None),  
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    request: Request = None,
):
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Можно загружать только изображения",
        )

    photo_id = uuid4()
    jpeg_rel_path = f"user_photos/{current_user.id}/{photo_id}.jpg"
    jpeg_path = MEDIA_ROOT / jpeg_rel_path

    jpeg_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        image = Image.open(file.file)
        rgb_image = image.convert("RGB")
        rgb_image.save(jpeg_path, format="JPEG", quality=90)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Не удалось прочитать файл как изображение",
        )

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
            "original_path": jpeg_rel_path,
            "processed_path": None,
            "preview_path": None,
            "mime_type": "image/jpeg",
            "file_size": jpeg_path.stat().st_size,
            "telegram_file_id": telegram_file_id,  # ← НОВОЕ
        },
    )
    await db.commit()

    base_url = settings.public_base_url.rstrip("/")
    url = f"{base_url}/media/{jpeg_rel_path}"

    return {"message": "Фото загружено", "photo_id": str(photo_id), "url": url}

@router.get("/")
async def list_photos(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    request: Request = None,
) -> Dict[str, Any]:
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

    base_url = settings.public_base_url.rstrip("/")

    items = [
        {
            "id": str(row["id"]),
            "url": f"{base_url}/media/{row['original_path']}",
            "telegram_file_id": row["telegram_file_id"],  # ← НОВОЕ
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
    """
    Удаляет все фото текущего пользователя (мягкое удаление: is_active = FALSE)
    """
    await db.execute(
        text(
            """
            UPDATE user_photos
            SET is_active = FALSE
            WHERE user_id = :user_id
            """
        ),
        {"user_id": str(current_user.id)},
    )
    await db.commit()

    return {"message": "Все фото удалены"}