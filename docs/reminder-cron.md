# Service reminder sweep — deployment

The reminder engine only does anything if something calls it on a schedule.
Until this is set up, the 30 / 7 / 1 / 0-day escalation in the concept document
sends **zero** notifications: the rules exist, the events exist, nothing runs.

## The command

```
python -m app.jobs.run_due_reminders
```

Runs every active notification rule once, then exits. Prints one structured
summary line and exits `0`; exits `1` only when the sweep could not start at
all (no database, bad configuration). An individual rule that fails is logged
and reported in `errors` without stopping the others — one misconfigured
marketing rule must not silence every service reminder.

### Why a command and not the HTTP endpoint

`POST /admin/notifications/rules/run-due` exists and still works for a manual
"run it now" from the admin portal. It is guarded by `CurrentAdmin`, so
pointing a scheduler at it means minting a long-lived admin JWT and storing it
in an environment variable — a standing administrator credential, visible in
deploy logs and shell sessions, whose only purpose is to trigger a task the
container can already perform itself.

The command runs in the same image with the same `DATABASE_URL` and needs no
credential.

## Railway

Railway runs cron jobs as a **separate service** off the same repo:

1. New service → same repo → same environment variables as the API
   (`DATABASE_URL` above all).
2. Set **Custom Start Command**:
   `python -m app.jobs.run_due_reminders`
3. Set **Cron Schedule**: `0 8 * * *`

`0 8 * * *` is 08:00 UTC — 09:00 in Lagos (WAT, UTC+1, no daylight saving).
Deliberately mid-morning local time: reminders that land at 3am are read at
breakfast with a dozen other overnight notifications, and a service reminder
competing for attention is a service reminder ignored.

Railway cron services must exit. This one does.

## Running it more than once a day is safe

Every reminder is recorded in `reminder_dispatches`, keyed on
`(rule, vehicle, milestone, stage)`. A second run the same day finds the row
and sends nothing, so a retry, an overlapping run, or a manual trigger from
the admin portal cannot double-notify anyone.

This is not a nicety. Before that table existed, the due-soon query had **no
lower bound and no sent-log**: every vehicle whose service was overdue matched
on every single call. A daily cron pointed at the old code would have told the
same owner their service was due every day, forever. The feature was safe only
because nothing ran it.

## What the first run will do

`reminder_dispatches` is created empty — there is no history to backfill,
because no sweep has ever run. The first execution therefore sends each
in-window vehicle its current stage once.

That is intended: those customers have never been reminded at all. It is worth
knowing before you switch it on, because it is the only run that reaches every
eligible vehicle at once. To see the size of it first, run the command against
a database copy and read `notificationsCreated` in the summary line.

## Checking it works

The summary is logged as JSON so it can be charted and alerted on:

```
reminder sweep complete {"rulesEvaluated": 2, "notificationsCreated": 14, "errors": []}
```

Worth an alert: `errors` non-empty, or `rulesEvaluated` dropping to 0 (every
rule deactivated, or the sweep silently not running).

`notificationsCreated: 0` is normal and expected on most days — it means no
vehicle crossed a stage boundary, not that anything is broken.

## Cadence

Configured per rule, in `config.stages`, defaulting to `[30, 7, 1, 0]`:

```json
{ "stages": [30, 7, 1, 0], "deep_link": "/service/book" }
```

A vehicle receives each stage once, plus one nudge if it goes overdue, then
nothing further. `app/domains/notifications/cadence.py` holds the arithmetic
and `tests/test_reminder_cadence.py` covers the boundaries — including the
walk that proves one service produces five reminders over 45 days rather
than 45.
