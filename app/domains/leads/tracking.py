"""Customer-facing view of the sales pipeline.

The internal pipeline has seven stages (new → contacted → qualified →
proposal → negotiation, plus won/lost). Customers must not see that
vocabulary: "qualified" and "negotiation" describe how the dealership is
sizing up the customer, not how their enquiry is progressing, and showing
someone they are in "negotiation" invites them to negotiate against a
position we have not offered yet.

So the seven internal stages collapse into four customer-facing steps:

    Submitted → Under Review → In Progress → Converted / Closed

This module is pure — no database, no ORM, no FastAPI. That keeps the
mapping testable without a live Postgres, which matters because it decides
what a customer is allowed to see.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from app.domains.shared.enums import LeadStatus


class TrackingStage(str, Enum):
    """What the customer sees. Deliberately fewer states than LeadStatus."""

    submitted = "submitted"
    under_review = "under_review"
    in_progress = "in_progress"
    converted = "converted"
    closed = "closed"


#: The ordered lifecycle rendered as a progress tracker. `converted` and
#: `closed` are both step 4 — they are the two ways the same step ends.
STAGE_ORDER: tuple[TrackingStage, ...] = (
    TrackingStage.submitted,
    TrackingStage.under_review,
    TrackingStage.in_progress,
    TrackingStage.converted,
)

#: Internal stage → what we admit to the customer.
_STAGE_MAP: dict[LeadStatus, TrackingStage] = {
    LeadStatus.new: TrackingStage.submitted,
    # "contacted" and "qualified" are both an agent working out whether and
    # how to help — one visible state is enough.
    LeadStatus.contacted: TrackingStage.under_review,
    LeadStatus.qualified: TrackingStage.under_review,
    # "proposal" and "negotiation" both mean numbers are moving. Naming the
    # difference would reveal our position in the deal.
    LeadStatus.proposal: TrackingStage.in_progress,
    LeadStatus.negotiation: TrackingStage.in_progress,
    LeadStatus.won: TrackingStage.converted,
    LeadStatus.lost: TrackingStage.closed,
}

#: Neutral, non-committal customer copy. These are English source strings;
#: the mobile app translates them by `stage` key, so wording changes here do
#: not silently bypass localisation.
STAGE_LABELS: dict[TrackingStage, str] = {
    TrackingStage.submitted: "Submitted",
    TrackingStage.under_review: "Under Review",
    TrackingStage.in_progress: "In Progress",
    TrackingStage.converted: "Converted",
    TrackingStage.closed: "Closed",
}

STAGE_DESCRIPTIONS: dict[TrackingStage, str] = {
    TrackingStage.submitted: "We have received your enquiry.",
    TrackingStage.under_review: "A representative is reviewing your enquiry.",
    TrackingStage.in_progress: "We are working on your request.",
    TrackingStage.converted: "This enquiry is complete.",
    # Deliberately vague: `lost_reason` is internal and often candid
    # ("budget too low", "time waster"). The customer gets a neutral close.
    TrackingStage.closed: "This enquiry has been closed.",
}


def to_stage(status: LeadStatus) -> TrackingStage:
    """Map an internal pipeline status to its customer-facing stage."""
    return _STAGE_MAP[status]


def is_terminal(stage: TrackingStage) -> bool:
    return stage in (TrackingStage.converted, TrackingStage.closed)


def step_index(stage: TrackingStage) -> int:
    """0-based position in the four-step tracker.

    `closed` has no slot of its own — it ends the tracker at the same step
    `converted` would, so the UI renders four steps either way and colours
    the last one by outcome.
    """
    if stage is TrackingStage.closed:
        return len(STAGE_ORDER) - 1
    return STAGE_ORDER.index(stage)


@dataclass(frozen=True)
class TimelineEntry:
    """One dated event in a lead's history."""

    stage: TrackingStage | None
    title: str
    body: str | None
    at: datetime
    #: True when written by a representative rather than derived from a
    #: status change — the app styles these as notes, not tracker steps.
    is_note: bool = False


def build_timeline(
    *,
    created_at: datetime,
    status: LeadStatus,
    events: list[tuple[LeadStatus, datetime]],
    notes: list[tuple[str, datetime, str | None]],
    won_at: datetime | None = None,
    lost_at: datetime | None = None,
) -> list[TimelineEntry]:
    """Assemble the history a customer is allowed to read, oldest first.

    `events` are recorded transitions. Leads created before status events
    existed have none, so the submission and any terminal outcome are
    synthesised from the timestamps the row always carries — otherwise an
    older lead would show an empty history.

    `notes` must ALREADY be filtered to customer-visible ones; this function
    does not re-check, and passing internal notes here would leak them.
    """
    entries: list[TimelineEntry] = [
        TimelineEntry(
            stage=TrackingStage.submitted,
            title=STAGE_LABELS[TrackingStage.submitted],
            body=STAGE_DESCRIPTIONS[TrackingStage.submitted],
            at=created_at,
        )
    ]

    # Collapse consecutive internal stages that map to the same customer
    # stage: contacted→qualified is one visible move, not two identical rows.
    last_stage = TrackingStage.submitted
    for internal, at in sorted(events, key=lambda e: e[1]):
        stage = to_stage(internal)
        if stage is last_stage:
            continue
        entries.append(
            TimelineEntry(
                stage=stage,
                title=STAGE_LABELS[stage],
                body=STAGE_DESCRIPTIONS[stage],
                at=at,
            )
        )
        last_stage = stage

    # Backfill a terminal entry for leads whose outcome predates event logging.
    current = to_stage(status)
    if is_terminal(current) and last_stage is not current:
        at = won_at if current is TrackingStage.converted else lost_at
        if at is not None:
            entries.append(
                TimelineEntry(
                    stage=current,
                    title=STAGE_LABELS[current],
                    body=STAGE_DESCRIPTIONS[current],
                    at=at,
                )
            )

    for body, at, author in notes:
        entries.append(
            TimelineEntry(
                stage=None,
                title=author or "Update from your representative",
                body=body,
                at=at,
                is_note=True,
            )
        )

    return sorted(entries, key=lambda e: e.at)
