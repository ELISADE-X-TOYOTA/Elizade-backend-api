from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.database import Base, engine, SessionLocal
from app.core.migrations import run_startup_migrations
from app.core.seed import seed_all
from app.domains.registry import *  # noqa: F403 — register all ORM models before routers
from app.api.v1.router import api_router

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    run_startup_migrations(engine)
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
    # Expo Go / Metro dev server on LAN (e.g. http://10.15.146.12:8081)
    allow_origin_regex=r"https?://(localhost|127\.0\.0\.1|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|192\.168\.\d{1,3}\.\d{1,3})(:\d+)?",
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
