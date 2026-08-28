from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import func
import logging

from sqlalchemy.orm import Session

from app.domains.customers.models import OwnedVehicle
from app.domains.notifications.dispatcher import dispatch_to_user
from app.domains.notifications.cadence import OVERDUE_STAGE, parse_stages, stage_for, stage_label
from app.domains.notifications.models import (
    BroadcastCampaign,
    NotificationRule,
    ReminderDispatch,
    UserNotification,
)
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

logger = logging.getLogger("elizade.notifications")


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


def _users_for_service_due_soon(
    db: Session, *, days: int, now: datetime | None = None
) -> list[tuple[User, OwnedVehicle]]:
    """Vehicles inside the reminder window.

    The lower bound is the important half. This filter used to be
    `next_service_due <= deadline` with nothing below it, so a vehicle overdue
    by two years matched every single sweep — harmless while nothing ran the
    sweep, and a daily mailshot to every lapsed owner the moment a cron did.
    """
    moment = now or datetime.now(timezone.utc)
    deadline = moment + timedelta(days=days)
    # Reminders stop this far past the due date; `cadence.stage_for` applies
    # the same cut-off, and the two must agree or the query returns rows that
    # are then silently discarded.
    floor = moment + timedelta(days=OVERDUE_STAGE)
    return (
        db.query(User, OwnedVehicle)
        .join(OwnedVehicle, OwnedVehicle.user_id == User.id)
        .filter(
            User.role == UserRole.customer,
            User.is_active.is_(True),
            OwnedVehicle.next_service_due.isnot(None),
            OwnedVehicle.next_service_due <= deadline,
            OwnedVehicle.next_service_due >= floor,
        )
        .all()
    )


def _already_sent(db: Session, *, rule_id: str, vehicle_id: str, milestone: datetime, stage: int) -> bool:
    """Has this exact reminder already gone out?

    Keyed on the milestone (the due date it was about) so that servicing the
    vehicle — which moves `next_service_due` — starts a fresh cycle rather
    than being suppressed by last cycle's rows.
    """
    return (
        db.query(ReminderDispatch.id)
        .filter(
            ReminderDispatch.rule_id == rule_id,
            ReminderDispatch.owned_vehicle_id == vehicle_id,
            ReminderDispatch.milestone == milestone,
            ReminderDispatch.stage == stage,
        )
        .first()
        is not None
    )


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


def evaluate_rule(db: Session, rule_id: str, *, now: datetime | None = None) -> RuleEvaluateOut:
    """Run one rule.

    `now` is injectable so the escalation can be tested by advancing the CLOCK
    against a fixed due date — which is what a daily cron actually does. The
    obvious alternative, moving the due date closer on each run, is not the
    same thing at all: the due date IS the de-duplication key, so shifting it
    reads as the customer rescheduling the service and correctly starts a new
    reminder cycle every time.
    """
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
        stages = parse_stages(config.get("stages"))
        # `days_before` is still honoured as the widest window so existing
        # rules keep working, but the stages decide who is actually told.
        window = int(config.get("days_before", max(stages)))
        now = now or datetime.now(timezone.utc)
        pairs = _users_for_service_due_soon(db, days=window, now=now)
        matched = len({user.id for user, _ in pairs})

        for user, vehicle in pairs:
            milestone = vehicle.next_service_due
            if milestone is None:
                continue
            stage = stage_for(milestone, now, stages)
            # Outside every configured step — nothing to say yet.
            if stage is None:
                continue
            # Already told them about this milestone at this step.
            if _already_sent(db, rule_id=rule.id, vehicle_id=vehicle.id, milestone=milestone, stage=stage):
                continue

            title = config.get("title") or "Service reminder"
            body = config.get("body") or (
                f"Your {vehicle.year} {vehicle.make} {vehicle.model} "
                f"({vehicle.registration_number}) {stage_label(stage)} for service."
            )
            # PER-RECIPIENT isolation, not just per-rule.
            #
            # `dispatch_to_user` writes the in-app row first and then attempts
            # email, so a single bounced or suppressed address raised straight
            # out of this loop and abandoned the whole rule — every remaining
            # customer went untold because of one bad address, and the one who
            # triggered it lost their in-app copy to the rollback as well.
            # A live run against production data failed exactly this way.
            try:
                result = dispatch_to_user(
                    db,
                    user=user,
                    title=title,
                    body=body,
                    category=NotificationCategory.service,
                    channels=list(rule.channels or []),
                    deep_link=config.get("deep_link", "/service/book"),
                )
            except Exception:  # noqa: BLE001 — one address must not stop the sweep
                logger.exception(
                    "reminder dispatch failed for user %s vehicle %s", user.id, vehicle.id
                )
                # Marked as sent regardless. The alternative is retrying a
                # permanently dead address every night for the rest of the
                # vehicle's life, which alerts nobody and fixes nothing; the
                # failure itself is already recorded per channel.
                db.add(
                    ReminderDispatch(
                        rule_id=rule.id,
                        user_id=user.id,
                        owned_vehicle_id=vehicle.id,
                        milestone=milestone,
                        stage=stage,
                    )
                )
                continue
            # Recorded even when a channel failed: the customer either has the
            # in-app record or the delivery log has the failure, and re-sending
            # the whole reminder tomorrow because SMS was down is worse than
            # missing one channel.
            db.add(
                ReminderDispatch(
                    rule_id=rule.id,
                    user_id=user.id,
                    owned_vehicle_id=vehicle.id,
                    milestone=milestone,
                    stage=stage,
                )
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
            # Same per-recipient isolation as the service branch above: one
            # suppressed address must not cancel a campaign to everyone else.
            try:
                result = dispatch_to_user(
                    db,
                    user=user,
                    title=title,
                    body=body,
                    category=NotificationCategory.promo,
                    channels=list(rule.channels or []),
                    deep_link=config.get("deep_link"),
                )
            except Exception:  # noqa: BLE001
                logger.exception("campaign dispatch failed for user %s", user.id)
                continue
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


def evaluate_due_rules(db: Session, *, now: datetime | None = None) -> dict:
    """Run every active rule once. Intended for a scheduled caller.

    There is no in-process scheduler on purpose: a dealership's reminder volume
    does not justify a broker and worker fleet, and a cron hitting one endpoint
    is a thing an ops person can see, run by hand and reason about. Point a
    daily job at `POST /admin/notifications/rules/run-due`.

    Failures are per-rule: one bad rule must not stop the rest of the sweep.
    """
    rules = db.query(NotificationRule).filter(NotificationRule.is_active.is_(True)).all()
    evaluated = 0
    notifications = 0
    errors: list[str] = []

    for rule in rules:
        try:
            result = evaluate_rule(db, rule.id, now=now)
            evaluated += 1
            notifications += getattr(result, "notificationsCreated", 0) or 0
        except HTTPException as exc:
            # An unsupported trigger_key is a configuration problem, not an outage.
            errors.append(f"{rule.name}: {exc.detail}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("rule %s failed", rule.id)
            errors.append(f"{rule.name}: {exc}")

    return {"rulesEvaluated": evaluated, "notificationsCreated": notifications, "errors": errors}
