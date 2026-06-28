from pydantic import BaseModel, ConfigDict, Field


VALID_TRIGGER_KEYS = frozenset(
    {
        "service_due_soon",
        "marketing_opt_in",
    }
)

VALID_SEGMENT_KEYS = frozenset(
    {
        "all_customers",
        "has_vehicle",
        "no_vehicle",
        "marketing_opt_in",
        "active_customers",
    }
)

VALID_CHANNELS = frozenset({"in_app", "email", "push"})


class NotificationRuleOut(BaseModel):
    id: str
    name: str
    triggerKey: str
    channels: list[str]
    cadence: str
    isActive: bool
    config: dict | None = None

    @staticmethod
    def from_model(rule) -> "NotificationRuleOut":
        return NotificationRuleOut(
            id=rule.id,
            name=rule.name,
            triggerKey=rule.trigger_key,
            channels=list(rule.channels or []),
            cadence=rule.cadence,
            isActive=rule.is_active,
            config=rule.config,
        )


class NotificationRuleCreateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(min_length=1, max_length=200)
    trigger_key: str = Field(alias="triggerKey", min_length=1, max_length=100)
    channels: list[str] = Field(min_length=1)
    cadence: str = Field(default="immediate", max_length=100)
    is_active: bool = Field(default=True, alias="isActive")
    config: dict | None = None


class NotificationRuleUpdateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = Field(default=None, max_length=200)
    channels: list[str] | None = None
    cadence: str | None = Field(default=None, max_length=100)
    is_active: bool | None = Field(default=None, alias="isActive")
    config: dict | None = None


class RuleEvaluateOut(BaseModel):
    ruleId: str
    matchedUsers: int
    notificationsCreated: int
    emailsSent: int
    pushesSent: int


class BroadcastCampaignOut(BaseModel):
    id: str
    title: str
    body: str
    segmentKey: str
    channels: list[str]
    status: str
    reachCount: int
    scheduledAt: str | None = None
    sentAt: str | None = None

    @staticmethod
    def from_model(campaign) -> "BroadcastCampaignOut":
        return BroadcastCampaignOut(
            id=campaign.id,
            title=campaign.title,
            body=campaign.body,
            segmentKey=campaign.segment_key,
            channels=list(campaign.channels or []),
            status=campaign.status.value,
            reachCount=campaign.reach_count,
            scheduledAt=campaign.scheduled_at.isoformat() if campaign.scheduled_at else None,
            sentAt=campaign.sent_at.isoformat() if campaign.sent_at else None,
        )


class BroadcastCampaignCreateIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1)
    segment_key: str = Field(alias="segmentKey", min_length=1, max_length=100)
    channels: list[str] = Field(min_length=1)
    scheduled_at: str | None = Field(default=None, alias="scheduledAt")


class CampaignSendOut(BaseModel):
    campaignId: str
    status: str
    reachCount: int
    notificationsCreated: int
    emailsSent: int
    pushesSent: int


class UserNotificationOut(BaseModel):
    id: str
    title: str
    body: str
    category: str
    isRead: bool
    deepLink: str | None = None
    createdAt: str

    @staticmethod
    def from_model(row) -> "UserNotificationOut":
        return UserNotificationOut(
            id=row.id,
            title=row.title,
            body=row.body,
            category=row.category.value,
            isRead=row.is_read,
            deepLink=row.deep_link,
            createdAt=row.created_at.isoformat(),
        )


class MarkReadOut(BaseModel):
    id: str
    isRead: bool


class MarkAllReadOut(BaseModel):
    updated: int
