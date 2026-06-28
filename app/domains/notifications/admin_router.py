from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import CurrentAdmin, StaffPortalUser
from app.domains.notifications import service
from app.domains.notifications.schemas import (
    BroadcastCampaignCreateIn,
    BroadcastCampaignOut,
    CampaignSendOut,
    NotificationRuleCreateIn,
    NotificationRuleOut,
    NotificationRuleUpdateIn,
    RuleEvaluateOut,
)

router = APIRouter(prefix="/admin/notifications", tags=["admin-notifications"])


@router.get("/rules", response_model=list[NotificationRuleOut])
def list_rules(_: StaffPortalUser, db: Session = Depends(get_db)) -> list[NotificationRuleOut]:
    return service.list_rules(db)


@router.post("/rules", response_model=NotificationRuleOut, status_code=201)
def create_rule(
    payload: NotificationRuleCreateIn,
    current_user: CurrentAdmin,
    db: Session = Depends(get_db),
) -> NotificationRuleOut:
    return service.create_rule(db, payload, created_by_id=current_user.id)


@router.patch("/rules/{rule_id}", response_model=NotificationRuleOut)
def update_rule(
    rule_id: str,
    payload: NotificationRuleUpdateIn,
    _: CurrentAdmin,
    db: Session = Depends(get_db),
) -> NotificationRuleOut:
    return service.update_rule(db, rule_id, payload)


@router.post("/rules/{rule_id}/evaluate", response_model=RuleEvaluateOut)
def evaluate_rule(
    rule_id: str,
    _: CurrentAdmin,
    db: Session = Depends(get_db),
) -> RuleEvaluateOut:
    return service.evaluate_rule(db, rule_id)


@router.get("/campaigns", response_model=list[BroadcastCampaignOut])
def list_campaigns(_: StaffPortalUser, db: Session = Depends(get_db)) -> list[BroadcastCampaignOut]:
    return service.list_campaigns(db)


@router.post("/campaigns", response_model=BroadcastCampaignOut, status_code=201)
def create_campaign(
    payload: BroadcastCampaignCreateIn,
    current_user: CurrentAdmin,
    db: Session = Depends(get_db),
) -> BroadcastCampaignOut:
    return service.create_campaign(db, payload, created_by_id=current_user.id)


@router.post("/campaigns/{campaign_id}/send", response_model=CampaignSendOut)
def send_campaign(
    campaign_id: str,
    _: CurrentAdmin,
    db: Session = Depends(get_db),
) -> CampaignSendOut:
    return service.send_campaign(db, campaign_id)
