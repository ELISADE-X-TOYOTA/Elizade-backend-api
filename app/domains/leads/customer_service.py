"""Read-only lead access for the customer who owns the lead.

Every query here filters on `customer_id == current_user.id`. That is the
whole security model, so it is done in one place rather than at each call
site: a lead is linked to a user account by `customer_id`, and a lead with a
NULL `customer_id` (a showroom walk-in captured by name and phone) belongs to
nobody and is therefore never returned.

Matching on phone or email instead was considered and rejected — an
unverified email on a walk-in lead would let anyone who registers with that
address read a stranger's enquiry history.
"""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domains.leads.customer_schemas import (
    CustomerLeadDetailOut,
    CustomerLeadOut,
    LeadAgentBrief,
    LeadTimelineEntryOut,
    LeadTrackerStepOut,
    LeadVehicleBrief,
)
from app.domains.leads.models import Lead, LeadNote, LeadStatusEvent
from app.domains.leads.tracking import (
    STAGE_LABELS,
    STAGE_ORDER,
    TrackingStage,
    build_timeline,
    is_terminal,
    step_index,
    to_stage,
)
from app.domains.shared.enums import LeadStatus


def _base_row(lead: Lead) -> dict:
    stage = to_stage(lead.status)
    idx = step_index(stage)
    return {
        "id": lead.id,
        "interestedModel": lead.interested_model,
        "stage": stage,
        "stageLabel": STAGE_LABELS[stage],
        "stageDescription": _description(stage),
        "stepIndex": idx,
        "stepCount": len(STAGE_ORDER),
        "isTerminal": is_terminal(stage),
        "isConverted": stage is TrackingStage.converted,
        "vehicle": (
            LeadVehicleBrief(
                id=lead.vehicle.id,
                make=lead.vehicle.make,
                model=lead.vehicle.model,
                year=lead.vehicle.year,
            )
            if lead.vehicle
            else None
        ),
        "assignedAgent": (
            LeadAgentBrief(
                firstName=lead.assigned_agent.first_name,
                lastName=lead.assigned_agent.last_name,
            )
            if lead.assigned_agent
            else None
        ),
        "createdAt": lead.created_at,
        "updatedAt": lead.updated_at,
    }


def _description(stage: TrackingStage) -> str:
    from app.domains.leads.tracking import STAGE_DESCRIPTIONS

    return STAGE_DESCRIPTIONS[stage]


def list_my_leads(db: Session, user_id: str) -> list[CustomerLeadOut]:
    """Every lead belonging to this customer, most recently updated first."""
    rows = (
        db.execute(
            select(Lead)
            .where(Lead.customer_id == user_id)
            .options(selectinload(Lead.vehicle), selectinload(Lead.assigned_agent))
            .order_by(Lead.updated_at.desc())
        )
        .scalars()
        .all()
    )
    return [CustomerLeadOut(**_base_row(lead)) for lead in rows]


def get_my_lead(db: Session, user_id: str, lead_id: str) -> CustomerLeadDetailOut:
    """One lead with its tracker and history.

    Returns 404 — not 403 — when the lead exists but belongs to someone else.
    A 403 would confirm the ID is real, which is enough to probe for other
    customers' leads.
    """
    lead = (
        db.execute(
            select(Lead)
            .where(Lead.id == lead_id, Lead.customer_id == user_id)
            .options(selectinload(Lead.vehicle), selectinload(Lead.assigned_agent))
        )
        .scalars()
        .first()
    )
    if not lead:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")

    events = (
        db.execute(
            select(LeadStatusEvent.status, LeadStatusEvent.created_at)
            .where(LeadStatusEvent.lead_id == lead.id)
            .order_by(LeadStatusEvent.created_at)
        )
        .tuples()
        .all()
    )

    # Only notes explicitly published to the customer. See LeadNote's docstring.
    note_rows = (
        db.execute(
            select(LeadNote)
            .where(LeadNote.lead_id == lead.id, LeadNote.is_customer_visible.is_(True))
            .options(selectinload(LeadNote.author))
            .order_by(LeadNote.created_at)
        )
        .scalars()
        .all()
    )
    notes = [
        (
            n.body,
            n.created_at,
            f"{n.author.first_name} {n.author.last_name}".strip() if n.author else None,
        )
        for n in note_rows
    ]

    timeline = build_timeline(
        created_at=lead.created_at,
        status=lead.status,
        events=[(LeadStatus(s), at) for s, at in events],
        notes=notes,
        won_at=lead.won_at,
        lost_at=lead.lost_at,
    )

    row = _base_row(lead)
    current_index = row["stepIndex"]
    stage = row["stage"]
    tracker = [
        LeadTrackerStepOut(
            stage=s,
            label=STAGE_LABELS[s],
            reached=i <= current_index,
            current=i == current_index,
        )
        for i, s in enumerate(STAGE_ORDER)
    ]
    # A closed lead reached the final step without converting; label it by
    # its real outcome so the UI does not claim a conversion that never happened.
    if stage is TrackingStage.closed:
        tracker[-1] = LeadTrackerStepOut(
            stage=TrackingStage.closed,
            label=STAGE_LABELS[TrackingStage.closed],
            reached=True,
            current=True,
        )

    return CustomerLeadDetailOut(
        **row,
        tracker=tracker,
        timeline=[
            LeadTimelineEntryOut(
                stage=e.stage, title=e.title, body=e.body, at=e.at, isNote=e.is_note
            )
            for e in timeline
        ],
    )
