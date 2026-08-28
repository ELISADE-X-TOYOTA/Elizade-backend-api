from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.core.database import Base, engine, SessionLocal
from app.core.deps import CurrentUser
from app.core.migrations import run_startup_migrations
from app.core.seed import seed_all
from app.domains.registry import *  # noqa: F403 — register all ORM models before routers
from app.domains.ownership.storage import storage
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

@app.get("/media/documents/{key}", include_in_schema=False)
def serve_document(key: str, _: CurrentUser) -> FileResponse:
    """Serve customer media only after bearer authentication.

    Documents are intentionally not mounted through ``StaticFiles``: that
    would make uploaded evidence public and would bypass the API's auth
    boundary. Storage keys are resolved by the storage backend, which rejects
    traversal and malformed paths.
    """
    path_for_key = getattr(storage, "path_for_key", None)
    if path_for_key is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    path = path_for_key(key)
    if path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media not found")
    content_type_for_key = getattr(storage, "content_type_for_key", None)
    media_type = content_type_for_key(key) if content_type_for_key else "application/octet-stream"
    return FileResponse(
        path,
        media_type=media_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
