from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TestDriveCreateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    vehicle_id: str = Field(alias="vehicleId")
    branch_id: str = Field(alias="branchId")
    scheduled_at: datetime = Field(alias="scheduledAt")
    notes: str | None = None


class TestDriveOut(BaseModel):
    id: str
    vehicleId: str
    vehicleLabel: str
    branchId: str
    branchName: str
    scheduledAt: str
    status: str
    notes: str | None = None
    leadId: str | None = None
    createdAt: str

    @staticmethod
    def from_model(booking) -> "TestDriveOut":
        vehicle = booking.vehicle
        branch = booking.branch
        vehicle_label = (
            f"{vehicle.year} {vehicle.make} {vehicle.model} {vehicle.trim}".strip()
            if vehicle
            else "Vehicle"
        )
        return TestDriveOut(
            id=booking.id,
            vehicleId=booking.vehicle_id,
            vehicleLabel=vehicle_label,
            branchId=booking.branch_id,
            branchName=branch.name if branch else "",
            scheduledAt=booking.scheduled_at.isoformat(),
            status=booking.status.value,
            notes=booking.notes,
            leadId=booking.lead_id,
            createdAt=booking.created_at.isoformat(),
        )
