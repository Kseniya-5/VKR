# Main FastAPI entrypoint. Kept as an alias so both uvicorn app.main:app
# and uvicorn app.api.main:app start the same application.
from app.api.main import app
