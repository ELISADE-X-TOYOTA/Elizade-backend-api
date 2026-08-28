from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class WarrantyClaimListItemOut(BaseModel):
    id: str
    claimType: str
    description: str
    attachmentUrls: list[str] = Field(default_factory=list)
    status: str
    customerId: str
    customerName: str
    vehicleLabel: str
    assignedToId: str | None = None
    assignedToName: str | None = None
    resolutionNotes: str | None = None
    createdAt: str
    updatedAt: str

    @staticmethod
    def from_model(claim) -> "WarrantyClaimListItemOut":
        vehicle = claim.owned_vehicle
        vehicle_label = f"{vehicle.year} {vehicle.make} {vehicle.model} ({vehicle.registration_number})"
        customer_name = f"{claim.customer.first_name} {claim.customer.last_name}".strip()
        assigned_name = None
        if claim.assigned_to:
            assigned_name = f"{claim.assigned_to.first_name} {claim.assigned_to.last_name}".strip()
        return WarrantyClaimListItemOut(
            id=claim.id,
            claimType=claim.claim_type,
            description=claim.description,
            attachmentUrls=list(claim.attachment_urls or []),
            status=claim.status.value,
            customerId=claim.user_id,
            customerName=customer_name,
            vehicleLabel=vehicle_label,
            assignedToId=claim.assigned_to_id,
            assignedToName=assigned_name,
            resolutionNotes=claim.resolution_notes,
            createdAt=claim.created_at.isoformat(),
            updatedAt=claim.updated_at.isoformat(),
        )


class PaginatedClaimsOut(BaseModel):
    items: list[WarrantyClaimListItemOut]
    total: int
    page: int
    size: int
    pages: int


class ClaimUpdateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str | None = None
    resolution_notes: Annotated[str | None, Field(alias="resolutionNotes")] = None
    assigned_to_id: Annotated[str | None, Field(alias="assignedToId")] = None


class ClaimCreateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    owned_vehicle_id: str = Field(alias="ownedVehicleId")
    claim_type: str = Field(alias="claimType", min_length=2, max_length=200)
    description: str = Field(min_length=10)
    conditions: str | None = Field(default=None, max_length=2000)
    current_mileage: Annotated[int | None, Field(alias="currentMileage", ge=0)] = None
    attachment_urls: Annotated[list[str], Field(alias="attachmentUrls", max_length=5)] = Field(default_factory=list)


class WarrantyEligibilityOut(BaseModel):
    eligible: bool
    reason: str | None = None
    inServiceDate: str | None = None
    coverageEnd: str | None = None
    mileageLimitKm: int
    warrantyMonths: int
    currentMileage: int
    certificateNumber: str | None = None
    batteryFreeMonths: int
    batteryPartialMonths: int
    batteryFreeCoverageEnd: str | None = None
    batteryPartialCoverageEnd: str | None = None
    batteryStatus: str
    batteryEligible: bool


class CustomerRecallOut(BaseModel):
    id: str
    recallId: str
    referenceCode: str
    title: str
    description: str
    severity: str
    vehicleLabel: str
    notifiedAt: str | None = None
    serviceCompletedAt: str | None = None
    isActive: bool


class WarrantySummaryOut(BaseModel):
    pendingClaims: int
    activeCertificates: int
    activeRecalls: int
    escalatedClaims: int


class OwnedVehicleOptionOut(BaseModel):
    id: str
    customerId: str
    customerName: str
    label: str
    registrationNumber: str
    vin: str

    @staticmethod
    def from_model(vehicle) -> "OwnedVehicleOptionOut":
        customer_name = f"{vehicle.owner.first_name} {vehicle.owner.last_name}".strip()
        label = f"{vehicle.year} {vehicle.make} {vehicle.model} ({vehicle.registration_number})"
        return OwnedVehicleOptionOut(
            id=vehicle.id,
            customerId=vehicle.user_id,
            customerName=customer_name,
            label=label,
            registrationNumber=vehicle.registration_number,
            vin=vehicle.vin,
        )


class WarrantyCertificateOut(BaseModel):
    id: str
    certificateNumber: str
    type: str
    status: str
    customerName: str
    vehicleLabel: str
    coverageStart: str
    coverageEnd: str
    coverageDetails: list[str]

    @staticmethod
    def from_model(row) -> "WarrantyCertificateOut":
        vehicle = row.owned_vehicle
        vehicle_label = f"{vehicle.year} {vehicle.make} {vehicle.model}"
        customer_name = f"{row.customer.first_name} {row.customer.last_name}".strip()
        return WarrantyCertificateOut(
            id=row.id,
            certificateNumber=row.certificate_number,
            type=row.type.value,
            status=row.status.value,
            customerName=customer_name,
            vehicleLabel=vehicle_label,
            coverageStart=row.coverage_start.isoformat(),
            coverageEnd=row.coverage_end.isoformat(),
            coverageDetails=list(row.coverage_details or []),
        )


class CertificateCreateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    owned_vehicle_id: str = Field(alias="ownedVehicleId")
    type: str = Field(default="standard")
    coverage_start: Annotated[str | None, Field(alias="coverageStart")] = None
    coverage_end: Annotated[str | None, Field(alias="coverageEnd")] = None
    coverage_details: Annotated[list[str], Field(alias="coverageDetails")] = Field(default_factory=list)


class RecallCampaignOut(BaseModel):
    id: str
    referenceCode: str
    title: str
    description: str
    severity: str
    affectedModels: list[str]
    affectedCount: int
    notifiedCount: int
    completedCount: int
    isActive: bool
    issuedAt: str

    @staticmethod
    def from_model(recall, *, affected: int, notified: int, completed: int) -> "RecallCampaignOut":
        return RecallCampaignOut(
            id=recall.id,
            referenceCode=recall.reference_code,
            title=recall.title,
            description=recall.description,
            severity=recall.severity.value,
            affectedModels=list(recall.affected_models or []),
            affectedCount=affected,
            notifiedCount=notified,
            completedCount=completed,
            isActive=recall.is_active,
            issuedAt=recall.issued_at.isoformat(),
        )


class RecallCreateIn(BaseModel):
    reference_code: str = Field(alias="referenceCode", min_length=3, max_length=50)
    title: str = Field(min_length=3, max_length=300)
    description: str = Field(min_length=3)
    severity: str = Field(default="medium")
    affected_models: Annotated[list[str], Field(alias="affectedModels")] = Field(default_factory=list)
    affected_year_from: Annotated[int | None, Field(alias="affectedYearFrom")] = None
    affected_year_to: Annotated[int | None, Field(alias="affectedYearTo")] = None


class RecallNotifyOut(BaseModel):
    recall: RecallCampaignOut
    notifiedCount: int
