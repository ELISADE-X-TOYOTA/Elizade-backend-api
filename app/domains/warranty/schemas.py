from pydantic import BaseModel, ConfigDict, Field


class WarrantyClaimListItemOut(BaseModel):
    id: str
    claimType: str
    description: str
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
    resolution_notes: str | None = Field(default=None, alias="resolutionNotes")
    assigned_to_id: str | None = Field(default=None, alias="assignedToId")


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
    coverage_start: str | None = Field(default=None, alias="coverageStart")
    coverage_end: str | None = Field(default=None, alias="coverageEnd")
    coverage_details: list[str] = Field(default_factory=list, alias="coverageDetails")


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
    affected_models: list[str] = Field(default_factory=list, alias="affectedModels")
    affected_year_from: int | None = Field(default=None, alias="affectedYearFrom")
    affected_year_to: int | None = Field(default=None, alias="affectedYearTo")


class RecallNotifyOut(BaseModel):
    recall: RecallCampaignOut
    notifiedCount: int
