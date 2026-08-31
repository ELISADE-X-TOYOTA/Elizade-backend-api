# Service Board — audit and implementation

Staff-facing digital service price book, per-vehicle maintenance status, and
customer call list. This document is the feature record: what already exists,
what Phase 1 changed, and what is still blocked.

The dashboard frontend is a **separate application in a separate repository**.
It is not part of this API repo, the customer mobile app, or the existing
admin portal (`elizade-web.vercel.app`). That admin portal is not in this
workspace and is not modified here.

---

## Current architecture relevant to the feature

Elizade Connect is one FastAPI backend (`app/domains/<domain>/`) serving:

| Client | Role | Auth |
|---|---|---|
| Customer mobile app (`Elizade-mobile-app`) | `customer` | Email OTP → JWT |
| Existing staff admin portal (not in this workspace) | `staff` / `admin` | Same OTP/JWT |
| Future Service Board (separate repo) | `staff` / `admin` | Same OTP/JWT; `StaffPortalUser` |

There is no Alembic. Tables are created with `Base.metadata.create_all` on
boot; additive changes for already-deployed databases live in
`app/core/migrations.py` as idempotent startup migrations.

### Service completion as it actually works

1. Customer books `POST /api/v1/service/appointments` (vehicle, branch,
   `serviceType` ∈ `periodic | repair | inspection | recall`, slot, mileage at
   booking, free-text `issueDescription`).
2. Staff confirm → start. Start creates a `ServiceJob` and seeds a **generic
   checklist** (`ServiceJobStage` labels such as "Oil & filter change"). Those
   labels are not a catalogue and are not recorded as work done.
3. Optional additional work is a free-text + cost request the customer
   approves or rejects.
4. Staff `PATCH .../appointments/{id}/status` with `{ "action": "complete" }`.
5. `_complete_job` writes **one** `service_history_items` row:

   - `performed_at` = now
   - `mileage` = **`mileage_at_booking`**, not a completion odometer
   - `description` = the booking's `issue_description`
   - `cost` = sum of approved additional-work items (invoice lines are the
     same free-text descriptions)
   - `service_type` = the appointment enum value (`periodic`, …)

Staff can also `POST /api/v1/admin/service/history` for walk-ins (same shape:
type, date, mileage, description, cost). Admin can delete a history row.

**The owned vehicle's `mileage` is not updated on completion.** Warranty claim
submission is currently the only staff/customer flow that writes
`owned_vehicles.mileage` after intake.

### What is not a service price book

- Inventory `vehicles.price` — showroom sale price.
- Sales `quotations` / `quotation_line_items` — vehicle deal quotes.
- `service_invoice_line_items` — billing snapshot of approved extra work,
  free-text, not versioned, not model/mileage-banded.

There is no service-item catalogue, no service groups beyond appointment-level
`ServiceType`, no mileage-band prices, and no interval table.

### Vehicle models

There is no `vehicle_models` table. A model is a string:

- Inventory `vehicles.model` (for sale)
- Garage `owned_vehicles.model` (after purchase / claim)

Seeded / physical-board names that already appear as strings include Corolla,
Camry, RAV4, Hilux, Yaris, Prado, Highlander, Fortuner, Sienna, Prius. The
board's Avensis, Coaster, Hiace are not special-cased anywhere.

### Mileage and reminders

| Field | Meaning |
|---|---|
| `owned_vehicles.mileage` | Latest known odometer (stale unless something writes it) |
| `owned_vehicles.next_service_due` / `next_service_mileage` | Opaque columns; reminder sweep keys off `next_service_due` only |
| `service_appointments.mileage_at_booking` | Customer-supplied at book time |
| `service_history_items.mileage` | Copied from booking, or staff-entered on a walk-in |

The reminder job (`python -m app.jobs.run_due_reminders`) is a 30/7/1/0-day
cadence against `next_service_due`. It is **not** per-item and does not use
structured history. The mobile garage currently **invents** a 5,000 km /
~6 month next-service milestone in `mapOwnedVehicle` because
`OwnedVehicleOut` does not expose the columns (README known gap).

### Auth roles that protect a staff dashboard

`UserRole`: `customer` | `staff` | `admin`.

- `StaffPortalUser` — admin **or** staff (existing admin service board,
  dashboard, CRM).
- `CurrentAdmin` — catalogue mutations, history deletion, bay create.

Do not invent a new role. Service Board uses the same JWT and
`StaffPortalUser` / `CurrentAdmin` split. Customer routers stay customer-only.

---

## Existing reusable components

Reuse these; do not duplicate them.

- **Domain layout** — `models.py` / `schemas.py` / `service.py` / `router.py`
- **Auth** — `StaffPortalUser`, `CurrentAdmin`, `CustomerUser`
- **IDs** — UUID strings; camelCase JSON, snake_case columns
- **Money** — `Numeric(14, 2)`, `Decimal`
- **Audit** — `AuditLog` (`entity_type`, `entity_id`, `changes` JSONB)
- **CSV import pattern** — `inventory.service.bulk_import_vehicles` (preview
  errors per row, savepoints). Price-book import in Phase 2 should follow it,
  with an extra publish/version step inventory does not have.
- **Warranty policy module** — `app/domains/warranty/policy.py` is the pattern
  for a future pure status engine (injected clock, reason string).
- **Owned vehicles, branches, customers, appointments, history parent rows**
- **Notification / reminder infrastructure** — leave unwired for Service Board
  call lists until Phase 3 + a product decision. Do not send customer
  notifications from the new dashboard.

Do **not** reuse as if they were structured work:

- `ServiceJobStage` (workflow checklist)
- `ServiceInvoiceLineItem` (invoice copy of extra-work text)
- `AdditionalWorkRequest.description` (free text)
- Sales quotations

---

## Confirmed data gaps

1. **No structured service-history line items.** Parent row is date + mileage
   + cost + free text. This is the Phase 1 blocker and is now being closed
   (see Phase 1 below). Historical rows remain unmapped on purpose.
2. **No canonical service-item catalogue.** Job stage labels are not items.
3. **No service prices, groups-as-data, mileage bands, or price versions.**
4. **No approved intervals** (km, months, due-soon thresholds, staleness).
   Phase 3 is blocked.
5. **Completion odometer is not captured.** History uses booking mileage.
   Phase 1 adds an optional completion mileage; existing clients can omit it.
6. **`owned_vehicles.mileage` is not updated on service complete.**
7. **Missing history is indistinguishable from “nothing needed.”** Any status
   engine must emit `NOT_ON_RECORD`, never `CURRENT`, when there is no line.
8. **Vehicle “model” is a free string**, not a controlled list. Price-book
   applicability in Phase 2 must validate against an explicit board-model
   list, not against live inventory rows (sold stock is the wrong grain).
9. **Admin portal UI is not in this workspace.** Completing a job with line
   items is an API capability; the existing web app must be updated separately
   (or staff attach lines after the fact from Service Board).
10. **Mobile must not grow customer-facing Service Board screens.** It already
    lists free-text history. Additive admin fields on admin endpoints do not
    affect it. Customer `/service/history` stays on the parent shape.

---

## Assumptions in the original spec that were incorrect

| Spec assumption | Actual system |
|---|---|
| Need to hunt for a hidden line-item table | Confirmed absent. Invoice lines and job stages are not it. |
| Service prices might already exist | They do not. Vehicle sale prices and extra-work costs are unrelated. |
| Vehicle models are first-class entities | They are strings on `vehicles` / `owned_vehicles`. |
| A new backend service might be required | It is not. Extend `app/domains/service/`. |
| Dashboard might be a module inside the existing web app | Product decision: **separate repo**. Existing admin portal stays the ops board (bays, jobs, extra work). |
| Historical free text can be mapped later with keywords | Explicitly forbidden. Dry-run reports unmapped rows; no bulk write. |
| `next_service_due` is a computed per-item status | It is a single timestamp used by reminders, often unset, not derived from history. |
| Mileage on the history row is “when the work was done” | It is booking mileage unless staff override on complete (Phase 1). |

No material conflict that would make Phase 1 destructive. Adding tables and
optional request fields is backward compatible. Do not rewrite
`service_history_items`. Do not delete descriptions.

---

## Architecture selected (and why)

**Extend the existing `service` domain in this API.** One database, one auth
story, one `/api/v1` prefix. A second backend would duplicate users, vehicles,
and JWT validation for no gain.

**Keep `service_history_items` as the parent visit record.** Date, mileage,
cost, and free-text notes already live there. Child rows (`service_history_lines`)
point at a catalogue item and an operation. They do **not** copy date/mileage.

**New catalogue table `service_items`**, not job stages and not invoice lines.
Groups are `periodic | chassis | engine` (board language), stored as an enum
on the item. Appointment `ServiceType` stays as-is (periodic/repair/inspection/recall).

**Operations** follow existing enum style (lowercase): `inspected`, `serviced`,
`repaired`, `replaced`. An inspection is never a replacement.

**Optional lines on complete** so today’s admin portal and today’s tests keep
working. Empty lines ⇒ those items will later show `NOT_ON_RECORD`. Staff can
`PUT` lines onto an existing history row from Service Board before the ops
UI catches up.

**Service Board = new frontend repo**, talking to this API with a staff JWT.
Do not add Service Board routes to the mobile app. Do not fold it into the
missing admin portal in this pass.

**Phase 2 prices** and **Phase 3 status** stay out of the schema until the
matrix and intervals are supplied. Catalogue + lines are the only new
persistence in Phase 1.

Naming vs the planning doc:

| Planning name | Actual table / type |
|---|---|
| `service_menu_items` | `service_items` (`ServiceItem`) |
| `service_history_lines` | `service_history_lines` (`ServiceHistoryLine`) |
| `service_menu_prices` | Phase 2 — not created |
| `service_intervals` | Phase 3 — not created |

---

## Proposed backend changes

### Phase 1 (this pass)

- Catalogue CRUD (admin write, staff read)
- `service_history_lines` with operation, optional quantity/amount/notes,
  source, backfill flags, `created_by_id`
- Complete appointment accepts optional `lines` + optional `mileage`
- Manual history create accepts optional `lines`
- `PUT /admin/service/history/{id}/lines` to attach/correct lines
- `GET /admin/service/history/{id}` for a single record with lines
- `unmappedOnly` on the history list (rows with zero lines)
- If completion mileage is **greater** than `owned_vehicles.mileage`, raise
  the vehicle odometer. Never decrease it from this flow.
- Dry-run unmapped report command — **writes nothing**
- No customer-endpoint change to history payload (no internal notes leak)
- No keyword backfill

### Phase 2 (after confirming no pricing model — confirmed none)

`service_item_prices` (or equivalent) with model applicability, mileage band,
currency (NGN), inclusive flag, effective dates, draft/published, version.
CSV import with preview, transactional publish, preserve previous version,
`AuditLog`. Reuse inventory bulk-import mechanics. Do not seed production
prices.

### Phase 3 (blocked)

Pure function, injected clock, returns status + reason. Must treat missing
lines as `NOT_ON_RECORD`. Must not mark inspect-only items replacement-overdue
without an approved rule.

---

## Proposed dashboard structure (separate repo)

Recommended path: `Elizade-service-board` (sibling of this API and the mobile
app). Stack should match the existing admin portal when that repo is
available; until then do not guess a design system.

First release, staff JWT only:

1. Overview (counts of unmapped history, due/overdue placeholders once Phase 3 exists)
2. Service price book (Phase 2)
3. Due-soon vehicles (Phase 3)
4. Overdue vehicles (Phase 3)
5. Customer call list (Phase 3; display only — no auto-call, no booking writes)
6. Vehicle maintenance details (Phase 3; Phase 1 can show raw history + lines)
7. Service-item management (Phase 1 API is ready)
8. Price import and publishing (Phase 2)
9. Interval configuration (Phase 3, after Elizade approval)
10. Branch / model / status filters
11. Export

CORS: add the dashboard origin to `CORS_ORIGINS` when it has a URL. Do not
expose catalogue write or price publish on customer routes.

---

## Required changes to existing applications

| App | Phase 1 | Later |
|---|---|---|
| **This API** | Catalogue + lines + optional complete payload | Prices, intervals, status endpoints |
| **Admin portal (not in workspace)** | Should send `lines` (and completion `mileage`) on complete; until then staff use `PUT .../history/{id}/lines` | Price import UI can live on Service Board instead |
| **Mobile** | None | Do not add staff screens. Do not invent intervals. Optional later: display customer-safe line summaries without notes/amounts |
| **Service Board repo** | Create separately; can list catalogue and attach lines to unmapped history | Price book, call list, status |

---

## Database migration plan

No Alembic. Follow `app/core/migrations.py`:

1. ORM models registered in `app/domains/registry.py` so `create_all` builds
   them on a fresh database.
2. Startup migration `_create_service_catalogue_tables` uses
   `__table__.create(..., checkfirst=True)` so an existing database gains the
   tables without dropping data.
3. New PostgreSQL enums: `service_item_group`, `service_operation`,
   `service_history_line_source`.
4. Reversible in the practical sense used here: tables are additive; dropping
   them is a manual rollback. No backfill writes. No `UPDATE` of
   `service_history_items.description`.
5. Indexes and uniqueness: see models. Tests use `drop_all` / `create_all` on
   the test database, so they pick up the new tables automatically.

---

## API contract plan

All under `/api/v1`. camelCase JSON.

**Catalogue (staff read, admin write)**

- `GET /admin/service/items?group=&isActive=`
- `POST /admin/service/items` (admin)
- `PATCH /admin/service/items/{id}` (admin)

**History (additive)**

- `GET /admin/service/history` — existing filters plus `unmappedOnly`; each
  item now includes `lines: []` (empty for old rows)
- `GET /admin/service/history/{id}` — new
- `POST /admin/service/history` — existing body plus optional `lines`
- `PUT /admin/service/history/{id}/lines` — replace the line set (staff)
- `DELETE /admin/service/history/{id}` — unchanged (admin); cascades lines

**Completion (backward compatible)**

`PATCH /admin/service/appointments/{id}/status`

```json
{ "action": "complete", "mileage": 45210, "lines": [
  { "serviceItemId": "...", "operation": "serviced", "quantity": 1, "amount": 0, "notes": null }
]}
```

`action` alone still completes, still writes the parent history row, still
notifies the customer. `lines` / `mileage` on confirm/start/cancel → 400.

**Customer**

- `GET /service/history` — **unchanged** parent fields only (no notes, no
  amounts, no backfill metadata).

**Not in Phase 1:** price-book read API, status engine, call list, CSV prices.

---

## Backward-compatibility strategy

- New tables only; parent history columns unchanged.
- New JSON fields are optional on input and additive on admin output.
- Existing complete tests send `{ "action": "complete" }` and still pass.
- Customer and mobile contracts unchanged.
- CRM `customers.schemas.ServiceHistoryItemOut` left untouched (unrelated
  surface).
- Free-text `description` remains the booking notes / walk-in narrative.
- Demo seed does **not** insert a fake production price book or a guessed
  Toyota menu. Tests create their own `ServiceItem` rows.

---

## Security and authorization

- Catalogue writes and price publishing (Phase 2): `CurrentAdmin`.
- Completing jobs, listing items, attaching lines: `StaffPortalUser`.
- History delete: `CurrentAdmin` (already).
- Customer tokens: 403 on all `/admin/service/*`.
- Line `notes` are staff-only. Do not add them to customer history.
- Validate item existence, uniqueness per visit, and operation enum on the
  server. UI checks are not sufficient.
- Future public price-board read (Phase 2) must not include draft prices,
  importer identity, or internal notes.

---

## Testing strategy

- Schema alias guard remains in `tests/test_schema_aliases.py`.
- New `tests/test_service_items.py` — auth, validation, uniqueness of `code`.
- Extend `tests/test_service_history.py` — lines on create, list includes
  lines, unmapped filter, PUT lines, GET by id, complete-with-lines,
  complete-without-lines still works, duplicate item rejected, inactive item
  rejected, customer history omits lines, mileage high-water mark.
- Existing appointment/job tests must stay green with `{ "action": "complete" }`.
- Dry-run job unit: unmapped count, zero writes.
- Phase 2/3 tests are not in this pass.

---

## Risks and unresolved business questions

**Blocked — Elizade must supply or approve before Phase 3**

- Interval km and months per item (or explicit “no fixed interval”)
- Applicable variants (Corolla vs Hilux vs …; trim or not)
- Whether each item is scheduled, inspection-based, condition-based, or repair-only
- Due-soon km and day thresholds
- Mileage staleness / estimated-mileage rules
- Baseline when the vehicle is new and has no history
- Whether an **inspection** ever creates a due/overdue replacement state

**Blocked — Phase 2**

- The actual ~200-cell price matrix (do not invent)
- Canonical model names as they should appear on the board (RAV-4 vs RAV4)
- Currency is assumed NGN; confirm
- Who may publish vs who may draft

**Operational**

- Existing admin portal is the job-completion UI and is not in this repo.
  Until it sends `lines`, every completed job is unmapped unless someone
  `PUT`s lines afterwards. Service Board should prioritize that queue.
- `owned_vehicles.next_service_due` will diverge from any future per-item
  engine. Reminders must not be silently switched over.
- Model strings will not match the physical board without a mapping table
  (Phase 2).
- Mobile still invents 5,000 km service intervals. Out of scope here; do not
  treat that figure as approved.

---

## File-by-file implementation sequence (Phase 1)

1. `docs/service-board.md` — this file
2. `app/domains/shared/enums.py` — groups, operations, line source
3. `app/domains/service/models.py` — `ServiceItem`, `ServiceHistoryLine`
4. `app/domains/registry.py` — register models
5. `app/core/migrations.py` — additive `checkfirst` create
6. `app/domains/service/schemas.py` — catalogue + line DTOs; optional complete fields
7. `app/domains/service/service.py` — catalogue, line writes, complete/manual/PUT
8. `app/domains/service/router.py` — new routes; pass actor into complete/create
9. `app/domains/service/backfill.py` — dry-run report, no writes
10. `app/jobs/report_unmapped_service_history.py` — CLI
11. `tests/test_service_items.py`, `tests/test_service_history.py`,
    `tests/test_service_history_backfill.py`
12. `README.md` — point at this doc; do not claim Phase 2/3 done

Phase 2 files (not now): price models, import service, publish transaction,
read-only board endpoint, CSV tests.

Phase 3 files (not now): `app/domains/service/status.py` (pure), interval
admin, due/overdue/call-list endpoints, injected-clock tests listed in the
spec.

---

## Phase 1 status

Implemented in this API: catalogue, structured lines, optional completion
payload, post-hoc line attach, unmapped listing, dry-run report.

Not implemented: dashboard frontend repo, price book, status engine, call
list, admin-portal UI, mobile changes, bulk text-to-item mapping.
