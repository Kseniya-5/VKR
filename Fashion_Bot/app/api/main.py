from fastapi import FastAPI

app = FastAPI(title="Fashion Bot API")


@app.get("/")
async def root():
    return {"message": "Fashion Bot API is running"}


@app.get("/health")
async def health():
    return {"status": "ok"}