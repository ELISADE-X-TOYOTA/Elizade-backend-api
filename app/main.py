import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from psycopg2 import errors
from sqlalchemy.exc import DataError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.services.email import mail_sender_warning
from app.core.database import Base, engine, SessionLocal
from app.core.deps import CurrentUser
from app.core.migrations import run_startup_migrations
from app.domains.auth import review_bypass
from app.core.seed import seed_all
from app.domains.registry import *  # noqa: F403 — register all ORM models before routers
from app.domains.ownership.storage import storage
from app.api.v1.router import api_router

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Refuse to start on a misconfigured reviewer bypass rather than boot with
    # a weak standing credential nobody notices. Announced either way — a back
    # door that starts silently is the kind that outlives its purpose.
    problems = review_bypass.validate_configuration()
    if problems:
        raise RuntimeError("Invalid reviewer configuration:\n  - " + "\n  - ".join(problems))
    review_bypass.log_status()

    # The From address is not a refusal condition — see `mail_sender_warning`.
    # Correcting it needs DNS and a verified Postmark sender first, so this
    # says so at boot instead of letting a customer be the one who notices.
    sender_warning = mail_sender_warning()
    if sender_warning:
        logging.getLogger("elizade.email").warning("[EMAIL] %s", sender_warning)

    Base.metadata.create_all(bind=engine)
    run_startup_migrations(engine)
    db = SessionLocal()
    try:
        seed_all(db)
    finally:
        db.close()
    yield


logger = logging.getLogger("elizade.main")

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

@app.exception_handler(DataError)
async def malformed_identifier(request: Request, exc: DataError) -> JSONResponse:
    """A client id Postgres cannot parse is a bad REQUEST, not a server fault.

    Every id in this API is a UUID column, and 173 places take one straight
    from the client into a query. Hand any of them something that is not a
    UUID — "undefined", an empty string, a demo id like `ov1` — and psycopg2
    raises `invalid input syntax for type uuid`, which nothing caught. The
    result was a 500, and the app renders 5xx as "Elizade services are
    temporarily unavailable", so a malformed id read to testers as an outage.

    That is exactly what happened: the telemetry captured nine of these,
    against `/warranty/eligibility`, `/warranty/claims` and
    `/auth/otp/request`, and every warranty screen was reported as down.

    Handled centrally rather than at 173 call sites, because the guard that
    has to be remembered every time is the guard that gets forgotten.

    NARROW ON PURPOSE. Only a malformed literal becomes a 400; any other
    `DataError` — a numeric overflow, a value too long for its column — is a
    real server-side fault and stays a 500, logged, rather than being dressed
    up as the client's mistake.
    """
    orig = getattr(exc, "orig", None)
    if isinstance(orig, errors.InvalidTextRepresentation):
        logger.warning("[REQUEST] malformed identifier on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "That identifier is not valid."},
        )

    logger.exception("[REQUEST] database rejected a value on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Something went wrong. Please try again."},
    )


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
