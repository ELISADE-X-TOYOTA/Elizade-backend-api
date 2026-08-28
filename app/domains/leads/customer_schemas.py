"""Customer-facing lead schemas.

Separate from `schemas.py` on purpose. The admin schemas expose `value`,
`lostReason`, the full note log and the agent's email — a customer-safe
response is not the admin response minus a couple of fields, and building it
by exclusion means the next field added to the admin schema leaks by default.
These models list what a customer MAY see, so new internal fields stay
invisible unless someone adds them here deliberately.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.domains.leads.tracking import TrackingStage


class LeadAgentBrief(BaseModel):
    """The representative, as much of them as a customer needs.

    No email or ID: the customer contacts the dealership through the app, not
    an agent's inbox, and an internal user ID is not theirs to hold.
    """

    firstName: str
    lastName: str


class LeadVehicleBrief(BaseModel):
    id: str
    make: str
    model: str
    year: int


class LeadTimelineEntryOut(BaseModel):
    """One dated event. `stage` is null for a representative's note."""

    stage: TrackingStage | None = None
    title: str
    body: str | None = None
    at: datetime
    isNote: bool = False


class LeadTrackerStepOut(BaseModel):
    """One step of the four-step progress tracker."""

    stage: TrackingStage
    label: str
    #: True once the lead has reached or passed this step.
    reached: bool
    #: True for the step the lead currently sits on.
    current: bool


class CustomerLeadOut(BaseModel):
    """List-row view."""

    id: str
    interestedModel: str
    stage: TrackingStage
    stageLabel: str
    stageDescription: str
    #: 0-based position in the tracker, so the app can render progress
    #: without duplicating the mapping rules.
    stepIndex: int
    stepCount: int
    isTerminal: bool
    #: Distinguishes the two terminal outcomes without exposing why.
    isConverted: bool
    vehicle: LeadVehicleBrief | None = None
    assignedAgent: LeadAgentBrief | None = None
    createdAt: datetime
    updatedAt: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class CustomerLeadDetailOut(CustomerLeadOut):
    """Detail view — adds the tracker and the readable history."""

    tracker: list[LeadTrackerStepOut]
    timeline: list[LeadTimelineEntryOut]
