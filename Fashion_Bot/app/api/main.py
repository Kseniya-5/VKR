from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.api.routes.auth import router as auth_router
from app.api.routes.users import router as users_router
from app.api.routes.photos import router as photos_router
from app.core.config import settings


app = FastAPI(
    title="Fashion Bot API",
    description="API for Telegram bot, web auth, account linking and user management.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MEDIA_ROOT = Path("/app/media")
MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(MEDIA_ROOT)), name="media")

app.include_router(auth_router)
app.include_router(users_router)
app.include_router(photos_router)


@app.get("/", tags=["system"])
async def root():
    return {
        "message": "Fashion Bot API is running",
        "docs": "/docs",
        "redoc": "/redoc",
        "openapi": "/openapi.json",
    }


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok"}
