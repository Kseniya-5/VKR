from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.api.routes.auth import router as auth_router
from app.api.routes.users import router as users_router
from app.api.routes.photos import router as photos_router

app = FastAPI(title="Fashion Bot API")

MEDIA_ROOT = Path("/app/media")
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)

app.mount("/media", StaticFiles(directory=str(MEDIA_ROOT)), name="media")

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(photos_router)

@app.get("/health")
async def health():
    return {"status": "ok"}