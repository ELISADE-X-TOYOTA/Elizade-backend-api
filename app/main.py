from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.database import Base, engine, SessionLocal
from app.core.seed import seed_all
from app.domains.registry import *  # noqa: F403 — register all ORM models

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_all(db)
    finally:
        db.close()
    yield


app = FastAPI(
    title="Elizade Connect API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

_uploads = Path("uploads/vehicles")
_uploads.mkdir(parents=True, exist_ok=True)
app.mount("/media/vehicles", StaticFiles(directory=str(_uploads)), name="vehicle-media")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
