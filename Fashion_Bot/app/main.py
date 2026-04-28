from fastapi import FastAPI
from app.api.routes.auth import router as auth_router

app = FastAPI(title="Fashion Bot API")

app.include_router(auth_router)


@app.get("/health")
async def health():
    return {"status": "ok"}