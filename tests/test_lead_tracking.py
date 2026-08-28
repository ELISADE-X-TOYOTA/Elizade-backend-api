"""The customer-facing lead lifecycle.

These guard a privacy boundary, not just a mapping. The internal pipeline
vocabulary ("qualified", "negotiation") and the internal fields (`value`,
`lostReason`, staff notes) must not reach a customer, and the default for a
lead note must stay closed. All pure — no database required.
"""

from datetime import datetime, timedelta, timezone

import pytest

from app.domains.leads.tracking import (
    STAGE_ORDER,
    TrackingStage,
    build_timeline,
    is_terminal,
    step_index,
    to_stage,
)
from app.domains.shared.enums import LeadStatus

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


def at(minutes: int) -> datetime:
    return NOW + timedelta(minutes=minutes)


# ── Stage mapping ────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "internal,expected",
    [
        (LeadStatus.new, TrackingStage.submitted),
        (LeadStatus.contacted, TrackingStage.under_review),
        (LeadStatus.qualified, TrackingStage.under_review),
        (LeadStatus.proposal, TrackingStage.in_progress),
        (LeadStatus.negotiation, TrackingStage.in_progress),
        (LeadStatus.won, TrackingStage.converted),
        (LeadStatus.lost, TrackingStage.closed),
    ],
)
def test_every_internal_status_maps_to_a_customer_stage(internal, expected):
    assert to_stage(internal) is expected


def test_mapping_is_exhaustive():
    """A new LeadStatus must not silently fall through to a KeyError."""
    for s in LeadStatus:
        assert to_stage(s) in TrackingStage


def test_internal_vocabulary_is_never_exposed():
    """Customers must not see how the dealership is sizing them up."""
    leaked = {"qualified", "negotiation", "proposal", "contacted"}
    assert {s.value for s in TrackingStage}.isdisjoint(leaked)


def test_tracker_has_four_steps():
    assert len(STAGE_ORDER) == 4


def test_closed_and_converted_share_the_final_step():
    """Both outcomes end the same tracker, so the UI renders four steps either way."""
    assert step_index(TrackingStage.closed) == step_index(TrackingStage.converted)
    assert step_index(TrackingStage.closed) == len(STAGE_ORDER) - 1


def test_steps_advance_in_order():
    assert [step_index(s) for s in STAGE_ORDER] == [0, 1, 2, 3]


def test_terminal_detection():
    assert is_terminal(TrackingStage.converted)
    assert is_terminal(TrackingStage.closed)
    assert not is_terminal(TrackingStage.submitted)
    assert not is_terminal(TrackingStage.under_review)
    assert not is_terminal(TrackingStage.in_progress)


# ── Timeline ─────────────────────────────────────────────────────────────


def test_timeline_always_opens_with_submission():
    tl = build_timeline(created_at=NOW, status=LeadStatus.new, events=[], notes=[])
    assert len(tl) == 1
    assert tl[0].stage is TrackingStage.submitted
    assert tl[0].at == NOW


def test_consecutive_events_mapping_to_one_stage_collapse():
    """contacted → qualified is one visible move, not two identical rows."""
    tl = build_timeline(
        created_at=NOW,
        status=LeadStatus.qualified,
        events=[(LeadStatus.contacted, at(10)), (LeadStatus.qualified, at(20))],
        notes=[],
    )
    stages = [e.stage for e in tl]
    assert stages == [TrackingStage.submitted, TrackingStage.under_review]


def test_distinct_stages_each_appear():
    tl = build_timeline(
        created_at=NOW,
        status=LeadStatus.negotiation,
        events=[
            (LeadStatus.contacted, at(10)),
            (LeadStatus.proposal, at(20)),
            (LeadStatus.negotiation, at(30)),
        ],
        notes=[],
    )
    assert [e.stage for e in tl] == [
        TrackingStage.submitted,
        TrackingStage.under_review,
        TrackingStage.in_progress,
    ]


def test_legacy_lead_without_events_still_shows_its_outcome():
    """Leads predating the event table must not render an empty history."""
    tl = build_timeline(
        created_at=NOW,
        status=LeadStatus.won,
        events=[],
        notes=[],
        won_at=at(90),
    )
    assert [e.stage for e in tl] == [TrackingStage.submitted, TrackingStage.converted]
    assert tl[-1].at == at(90)


def test_legacy_lost_lead_backfills_from_lost_at():
    tl = build_timeline(
        created_at=NOW, status=LeadStatus.lost, events=[], notes=[], lost_at=at(45)
    )
    assert tl[-1].stage is TrackingStage.closed


def test_terminal_entry_is_not_duplicated_when_already_recorded():
    tl = build_timeline(
        created_at=NOW,
        status=LeadStatus.won,
        events=[(LeadStatus.won, at(60))],
        notes=[],
        won_at=at(60),
    )
    assert [e.stage for e in tl].count(TrackingStage.converted) == 1


def test_closed_lead_never_states_a_reason():
    """`lost_reason` is internal and often candid — it must not surface."""
    tl = build_timeline(
        created_at=NOW, status=LeadStatus.lost, events=[], notes=[], lost_at=at(45)
    )
    assert "reason" not in (tl[-1].body or "").lower()


def test_notes_are_interleaved_chronologically():
    tl = build_timeline(
        created_at=NOW,
        status=LeadStatus.contacted,
        events=[(LeadStatus.contacted, at(30))],
        notes=[("We called you today.", at(15), "Amaka")],
    )
    assert [e.at for e in tl] == sorted(e.at for e in tl)
    note = [e for e in tl if e.is_note]
    assert len(note) == 1
    assert note[0].title == "Amaka"
    assert note[0].stage is None


def test_note_without_an_author_still_renders():
    tl = build_timeline(
        created_at=NOW,
        status=LeadStatus.new,
        events=[],
        notes=[("An update.", at(5), None)],
    )
    assert [e for e in tl if e.is_note][0].title


def test_timeline_is_sorted_oldest_first():
    tl = build_timeline(
        created_at=NOW,
        status=LeadStatus.negotiation,
        events=[(LeadStatus.negotiation, at(50)), (LeadStatus.contacted, at(10))],
        notes=[("Later note", at(70), "A"), ("Earlier note", at(5), "B")],
    )
    assert [e.at for e in tl] == sorted(e.at for e in tl)


# ── Schema surface ───────────────────────────────────────────────────────


def test_customer_schema_hides_internal_commercial_fields():
    """The customer response is an allowlist, not the admin schema minus a few keys."""
    from app.domains.leads.customer_schemas import CustomerLeadDetailOut

    fields = set(CustomerLeadDetailOut.model_fields)
    for banned in ("value", "lostReason", "notes", "source", "customerName", "phone", "email"):
        assert banned not in fields, f"{banned} must not be exposed to customers"


def test_agent_brief_exposes_no_contact_details():
    from app.domains.leads.customer_schemas import LeadAgentBrief

    assert set(LeadAgentBrief.model_fields) == {"firstName", "lastName"}


def test_lead_note_defaults_to_private():
    """The privacy guarantee: existing notes stay internal."""
    from app.domains.leads.models import LeadNote

    assert LeadNote.__table__.c.is_customer_visible.default.arg is False
    assert LeadNote.__table__.c.is_customer_visible.nullable is False
