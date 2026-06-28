from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.customers.models import OwnedVehicle
from app.domains.notifications.dispatcher import dispatch_to_user
from app.domains.notifications.models import BroadcastCampaign, NotificationRule, UserNotification
from app.domains.notifications.schemas import (
    VALID_CHANNELS,
    VALID_SEGMENT_KEYS,
    VALID_TRIGGER_KEYS,
    BroadcastCampaignCreateIn,
    BroadcastCampaignOut,
    CampaignSendOut,
    MarkReadOut,
    NotificationRuleCreateIn,
    NotificationRuleOut,
    NotificationRuleUpdateIn,
    RuleEvaluateOut,
    UserNotificationOut,
)
from app.domains.shared.enums import BroadcastCampaignStatus, NotificationCategory
from app.domains.users.models import DEFAULT_PREFERENCES, User, UserRole


def _validate_channels(channels: list[str]) -> list[str]:
    normalized = [c.strip().lower() for c in channels if c.strip()]
    invalid = set(normalized) - VALID_CHANNELS
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one channel is required")
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid channels: {', '.join(sorted(invalid))}",
        )
    return normalized


def list_rules(db: Session) -> list[NotificationRuleOut]:
    rows = db.query(NotificationRule).order_by(NotificationRule.created_at.desc()).all()
    return [NotificationRuleOut.from_model(r) for r in rows]


def create_rule(db: Session, payload: NotificationRuleCreateIn, *, created_by_id: str | None) -> NotificationRuleOut:
    trigger = payload.trigger_key.strip().lower()
    if trigger not in VALID_TRIGGER_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid trigger key '{trigger}'. Valid options: {', '.join(sorted(VALID_TRIGGER_KEYS))}",
        )
    channels = _validate_channels(payload.channels)
    rule = NotificationRule(
        name=payload.name.strip(),
        trigger_key=trigger,
        channels=channels,
        cadence=payload.cadence.strip() or "immediate",
        is_active=payload.is_active,
        config=payload.config,
        created_by_id=created_by_id,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return NotificationRuleOut.from_model(rule)


def update_rule(db: Session, rule_id: str, payload: NotificationRuleUpdateIn) -> NotificationRuleOut:
    rule = db.get(NotificationRule, rule_id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification rule not found")

    if payload.name is not None:
        rule.name = payload.name.strip()
    if payload.channels is not None:
        rule.channels = _validate_channels(payload.channels)
    if payload.cadence is not None:
        rule.cadence = payload.cadence.strip() or rule.cadence
    if payload.is_active is not None:
        rule.is_active = payload.is_active
    if payload.config is not None:
        rule.config = payload.config

    db.commit()
    db.refresh(rule)
    return NotificationRuleOut.from_model(rule)


def _customers_for_segment(db: Session, segment_key: str) -> list[User]:
    segment = segment_key.strip().lower()
    if segment not in VALID_SEGMENT_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid segment key '{segment}'. Valid options: {', '.join(sorted(VALID_SEGMENT_KEYS))}",
        )

    query = db.query(User).filter(User.role == UserRole.customer)
    if segment == "all_customers":
        pass
    elif segment == "has_vehicle":
        query = query.filter(User.owned_vehicles.any())
    elif segment == "no_vehicle":
        query = query.filter(~User.owned_vehicles.any())
    elif segment == "marketing_opt_in":
        query = query.filter(User.preferences["marketing_opt_in"].astext == "true")
    elif segment == "active_customers":
        query = query.filter(User.is_active.is_(True))

    return query.all()


def _users_for_service_due_soon(db: Session, *, days: int) -> list[tuple[User, OwnedVehicle]]:
    now = datetime.now(timezone.utc)
    deadline = now + timedelta(days=days)
    rows = (
        db.query(User, OwnedVehicle)
        .join(OwnedVehicle, OwnedVehicle.user_id == User.id)
        .filter(
            User.role == UserRole.customer,
            User.is_active.is_(True),
            OwnedVehicle.next_service_due.isnot(None),
            OwnedVehicle.next_service_due <= deadline,
        )
        .all()
    )
    return rows


def _users_for_marketing_trigger(db: Session) -> list[User]:
    return (
        db.query(User)
        .filter(
            User.role == UserRole.customer,
            User.is_active.is_(True),
            User.preferences["marketing_opt_in"].astext == "true",
        )
        .all()
    )


def evaluate_rule(db: Session, rule_id: str) -> RuleEvaluateOut:
    rule = db.get(NotificationRule, rule_id)
    if not rule:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification rule not found")
    if not rule.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Rule is inactive")

    config = rule.config or {}
    matched = 0
    notifications_created = 0
    emails_sent = 0
    pushes_sent = 0

    if rule.trigger_key == "service_due_soon":
        days = int(config.get("days_before", 14))
        pairs = _users_for_service_due_soon(db, days=days)
        matched = len({user.id for user, _ in pairs})
        for user, vehicle in pairs:
            title = config.get("title") or "Service reminder"
            body = config.get("body") or (
                f"Your {vehicle.year} {vehicle.make} {vehicle.model} "
                f"({vehicle.registration_number}) is due for service soon."
            )
            result = dispatch_to_user(
                db,
                user=user,
                title=title,
                body=body,
                category=NotificationCategory.service,
                channels=list(rule.channels or []),
                deep_link=config.get("deep_link", "/service/book"),
            )
            notifications_created += int(result.in_app_created)
            emails_sent += int(result.email_sent)
            pushes_sent += int(result.push_sent)
    elif rule.trigger_key == "marketing_opt_in":
        users = _users_for_marketing_trigger(db)
        matched = len(users)
        title = config.get("title") or rule.name
        body = config.get("body") or "Check out the latest offers from Elizade Toyota."
        for user in users:
            result = dispatch_to_user(
                db,
                user=user,
                title=title,
                body=body,
                category=NotificationCategory.promo,
                channels=list(rule.channels or []),
                deep_link=config.get("deep_link"),
            )
            notifications_created += int(result.in_app_created)
            emails_sent += int(result.email_sent)
            pushes_sent += int(result.push_sent)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Trigger '{rule.trigger_key}' is not supported for evaluation",
        )

    db.commit()
    return RuleEvaluateOut(
        ruleId=rule.id,
        matchedUsers=matched,
        notificationsCreated=notifications_created,
        emailsSent=emails_sent,
        pushesSent=pushes_sent,
    )


def list_campaigns(db: Session) -> list[BroadcastCampaignOut]:
    rows = db.query(BroadcastCampaign).order_by(BroadcastCampaign.created_at.desc()).all()
    return [BroadcastCampaignOut.from_model(c) for c in rows]


def create_campaign(
    db: Session,
    payload: BroadcastCampaignCreateIn,
    *,
    created_by_id: str | None,
) -> BroadcastCampaignOut:
    segment = payload.segment_key.strip().lower()
    if segment not in VALID_SEGMENT_KEYS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid segment key '{segment}'. Valid options: {', '.join(sorted(VALID_SEGMENT_KEYS))}",
        )
    channels = _validate_channels(payload.channels)
    scheduled_at = None
    if payload.scheduled_at:
        try:
            scheduled_at = datetime.fromisoformat(payload.scheduled_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid scheduledAt datetime") from exc

    audience = _customers_for_segment(db, segment)
    campaign = BroadcastCampaign(
        title=payload.title.strip(),
        body=payload.body.strip(),
        segment_key=segment,
        channels=channels,
        scheduled_at=scheduled_at,
        status=BroadcastCampaignStatus.scheduled if scheduled_at else BroadcastCampaignStatus.draft,
        reach_count=len(audience),
        created_by_id=created_by_id,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return BroadcastCampaignOut.from_model(campaign)


def send_campaign(db: Session, campaign_id: str) -> CampaignSendOut:
    campaign = db.get(BroadcastCampaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    if campaign.status == BroadcastCampaignStatus.sent:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Campaign has already been sent")
    if campaign.status == BroadcastCampaignStatus.cancelled:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Campaign is cancelled")

    audience = _customers_for_segment(db, campaign.segment_key)
    category = NotificationCategory.promo if campaign.segment_key == "marketing_opt_in" else NotificationCategory.system

    notifications_created = 0
    emails_sent = 0
    pushes_sent = 0

    campaign.status = BroadcastCampaignStatus.sending
    db.flush()

    for user in audience:
        result = dispatch_to_user(
            db,
            user=user,
            title=campaign.title,
            body=campaign.body,
            category=category,
            channels=list(campaign.channels or []),
            campaign_id=campaign.id,
        )
        notifications_created += int(result.in_app_created)
        emails_sent += int(result.email_sent)
        pushes_sent += int(result.push_sent)

    campaign.status = BroadcastCampaignStatus.sent
    campaign.sent_at = datetime.now(timezone.utc)
    campaign.reach_count = len(audience)
    db.commit()

    return CampaignSendOut(
        campaignId=campaign.id,
        status=campaign.status.value,
        reachCount=campaign.reach_count,
        notificationsCreated=notifications_created,
        emailsSent=emails_sent,
        pushesSent=pushes_sent,
    )


def list_user_notifications(db: Session, user_id: str, *, unread_only: bool = False) -> list[UserNotificationOut]:
    query = db.query(UserNotification).filter(UserNotification.user_id == user_id)
    if unread_only:
        query = query.filter(UserNotification.is_read.is_(False))
    rows = query.order_by(UserNotification.created_at.desc()).all()
    return [UserNotificationOut.from_model(r) for r in rows]


def mark_notification_read(db: Session, user_id: str, notification_id: str) -> MarkReadOut:
    row = (
        db.query(UserNotification)
        .filter(UserNotification.id == notification_id, UserNotification.user_id == user_id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    row.is_read = True
    db.commit()
    return MarkReadOut(id=row.id, isRead=True)


def mark_all_notifications_read(db: Session, user_id: str) -> int:
    updated = (
        db.query(UserNotification)
        .filter(UserNotification.user_id == user_id, UserNotification.is_read.is_(False))
        .update({UserNotification.is_read: True}, synchronize_session=False)
    )
    db.commit()
    return updated or 0


def unread_count(db: Session, user_id: str) -> int:
    return (
        db.query(func.count(UserNotification.id))
        .filter(UserNotification.user_id == user_id, UserNotification.is_read.is_(False))
        .scalar()
        or 0
    )
