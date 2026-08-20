# Elizade Connect — API

FastAPI backend for **Elizade Motors** (Toyota / Jetour / JAC, Nigeria). Serves
both the customer mobile app and the staff admin portal from one codebase:
inventory, sales, service, ownership, warranty, support, and notifications.

Python 3.12 · FastAPI · SQLAlchemy 2 · PostgreSQL 16 · Pydantic v2.

---

## Run it locally

**1. Start the database.** It runs in Docker on port **5435** (not 5432 — that
is usually taken by another local Postgres):

```bash
docker compose up -d db
```

**2. Start the API:**

```bash
./.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

(`--host 0.0.0.0`, not the default — a physical phone on your Wi-Fi cannot reach
a server bound to localhost.)

Interactive docs: <http://localhost:8000/docs>

> **`connection refused ... port 5435`** on startup means the database container
> isn't running. Run step 1. `docker ps` showing *other* projects' containers is
> not the same as yours being up — check with `docker compose ps db`.

On boot the app creates tables, runs startup migrations, and seeds demo data.

### Configuration

Copy `.env.example` to `.env` and adjust. Key values:

| Key | Notes |
|---|---|
| `DATABASE_URL` | Must use port **5435** to match `docker-compose.yml` |
| `JWT_SECRET` | Change before any deployment |
| `SMTP_*` | Optional. Unset ⇒ OTP codes print to the console |
| `CORS_ORIGINS` | Admin portal origin; the mobile LAN range is allowed by regex |

Without SMTP configured you'll see `[EMAIL] SMTP not configured — codes are
printed to the console instead.` on boot. That is expected in development: the
login OTP appears in the terminal.

---

## Tests

```bash
./.venv/Scripts/python.exe -m pytest -q
```

**338 tests.** They run against a real PostgreSQL database (not SQLite), so the
container must be up. Override the target with `TEST_DATABASE_URL`.

---

## Layout

```
app/
  main.py              app factory, lifespan (create_all → migrations → seed)
  api/v1/router.py     every router mounted here
  core/                config, database, security, deps, migrations, seed
  domains/<domain>/    models · schemas · service · router
  services/            email, push
tests/
uploads/               local media, served from /media/*
```

Each domain follows the same four-file shape. **Routers stay thin** — they
handle HTTP and delegate; business rules and permission checks live in
`service.py`, which is what the tests exercise.

Customer-facing and admin routes are separate routers with separate schemas
(`customer_router.py` / `router.py`). This is deliberate: it makes it hard to
leak an admin field into a customer response by widening a shared model.

### Auth

Email OTP, no passwords. `POST /auth/request-otp` → code by email → `POST
/auth/verify-otp` → JWT bearer token. Role is enforced by dependency:
`CustomerUser` rejects staff with 403, `AdminUser` the reverse.

### Migrations

No Alembic. `app/core/migrations.py` holds idempotent startup migrations that
inspect the schema and no-op when already applied. Suitable for dev; a real
migration tool is needed before production.

---

## API surface

105 paths — 40 customer-facing, the rest admin. Full schema at `/docs`.
Customer highlights:

| Area | Endpoints |
|---|---|
| Inventory | `GET /vehicles`, `GET /vehicles/{id}`, `GET /branches` (public) |
| Sales | test drives, quotations, reservations, trade-ins, watchlist |
| Service | book, list, track appointments; service history |
| Ownership | VIN lookup, ownership requests, `GET /ownership/vehicles` (garage) |
| Warranty | certificates, claims, recalls |
| Support | `GET|POST /support/tickets`, `/{id}`, `/{id}/messages`, `/{id}/rate`, `/attachments/upload` |
| Notifications | `GET /notifications?unreadOnly=`, `/{id}/read`, `/read-all` |
| Dashboard | `GET /dashboard/summary` |

Note: `GET /vehicles` omits `engine` and the whole `specs` bag — only the detail
endpoint returns them. Anything needing full specs (the mobile comparison
screen) must fetch per-vehicle.

---

## File uploads

`POST /support/attachments/upload` and `POST /ownership/documents/upload` take
multipart, store to `uploads/documents/`, and return a `/media/documents/<key>`
URL. Max 10 MB.

**Only JPEG, PNG, WebP and PDF are accepted** (415 otherwise), and the extension
is derived from the *content type*, not the uploaded filename. This matters:
files are served back from a static mount, so a stored `.html` or `.svg` would
execute as script on our own origin. SVG is excluded for exactly that reason.

Fields that accept attachment URLs (`attachments` on a ticket or reply) validate
that each URL came from our own storage — prefix **and** key shape. Without that
the field is an arbitrary-URL sink rendered by the staff console.

---

## Conventions

- **Scope every customer query by `user_id`.** Return **404**, not 403, when a
  row isn't theirs — a 403 confirms the id exists.
- **Respond with camelCase**, store snake_case. Pydantic schemas do the mapping.
- **Validate at the schema** where possible (`Field(ge=1, le=5)`), so bad input
  is rejected before it reaches a database lookup.
- Don't sort by `created_at` alone to identify a row. It defaults to `now()`,
  which is *transaction* time — rows written together carry identical
  timestamps. Use the id.

---

## Known gaps

- Startup migrations, not Alembic — see above.
- Demo `specs` are identical across all seeded vehicles, so the mobile
  comparison screen has little to differentiate. Real per-model specs needed.
- `OwnedVehicleOut` omits `nextServiceDue` / `nextServiceMileage` even though
  the columns exist; the mobile garage derives them.
- Uploads are stored on local disk. Fine for dev; needs object storage and an
  orphan-cleanup job for production (a file uploaded then abandoned is never
  collected).
