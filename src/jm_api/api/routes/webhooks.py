from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.orm import Session

from jm_api.api.deps import get_current_active_user
from jm_api.db.session import get_db
from jm_api.models.user import User
from jm_api.models.webhook import Webhook, WebhookDeliveryLog
from jm_api.schemas.webhook import (
    SUPPORTED_WEBHOOK_EVENT_TYPES,
    WebhookCreate,
    WebhookDeliveryLogResponse,
    WebhookResponse,
    WebhookUpdate,
)
from jm_api.services.webhooks import validate_webhook_url

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("", response_model=WebhookResponse, status_code=201)
def create_webhook(
    payload: WebhookCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> WebhookResponse:
    if not set(payload.event_types).issubset(SUPPORTED_WEBHOOK_EVENT_TYPES):
        raise HTTPException(status_code=400, detail="Unsupported webhook event type")
    try:
        validate_webhook_url(payload.target_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    webhook = Webhook(
        user_id=current_user.id,
        target_url=payload.target_url,
        event_types=payload.event_types,
        secret=payload.secret,
        is_active=True,
    )
    db.add(webhook)
    db.commit()
    db.refresh(webhook)
    return WebhookResponse.model_validate(webhook)


@router.get("", response_model=list[WebhookResponse])
def list_webhooks(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[WebhookResponse]:
    items = db.execute(
        select(Webhook)
        .where(Webhook.user_id == current_user.id)
        .order_by(Webhook.create_at.desc())
    ).scalars().all()
    return [WebhookResponse.model_validate(w) for w in items]


@router.patch("/{webhook_id}", response_model=WebhookResponse)
def update_webhook(
    payload: WebhookUpdate,
    webhook_id: str = Path(pattern=r"^[a-zA-Z0-9]{32}$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> WebhookResponse:
    webhook = db.execute(
        select(Webhook)
        .where(Webhook.id == webhook_id)
        .where(Webhook.user_id == current_user.id)
    ).scalar_one_or_none()
    if webhook is None:
        raise HTTPException(status_code=404, detail="Webhook not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "event_types" in update_data and update_data["event_types"] is not None:
        if not set(update_data["event_types"]).issubset(SUPPORTED_WEBHOOK_EVENT_TYPES):
            raise HTTPException(status_code=400, detail="Unsupported webhook event type")

    if "target_url" in update_data and update_data["target_url"] is not None:
        try:
            validate_webhook_url(update_data["target_url"])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    for field, value in update_data.items():
        setattr(webhook, field, value)

    db.commit()
    db.refresh(webhook)
    return WebhookResponse.model_validate(webhook)


@router.delete("/{webhook_id}", status_code=204)
def delete_webhook(
    webhook_id: str = Path(pattern=r"^[a-zA-Z0-9]{32}$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> None:
    webhook = db.execute(
        select(Webhook)
        .where(Webhook.id == webhook_id)
        .where(Webhook.user_id == current_user.id)
    ).scalar_one_or_none()
    if webhook is None:
        raise HTTPException(status_code=404, detail="Webhook not found")
    db.delete(webhook)
    db.commit()


@router.get("/{webhook_id}/deliveries", response_model=list[WebhookDeliveryLogResponse])
def list_delivery_logs(
    webhook_id: str = Path(pattern=r"^[a-zA-Z0-9]{32}$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
) -> list[WebhookDeliveryLogResponse]:
    webhook = db.execute(
        select(Webhook)
        .where(Webhook.id == webhook_id)
        .where(Webhook.user_id == current_user.id)
    ).scalar_one_or_none()
    if webhook is None:
        raise HTTPException(status_code=404, detail="Webhook not found")

    logs = db.execute(
        select(WebhookDeliveryLog)
        .where(WebhookDeliveryLog.webhook_id == webhook.id)
        .order_by(WebhookDeliveryLog.create_at.desc())
        .limit(100)
    ).scalars().all()
    return [WebhookDeliveryLogResponse.model_validate(item) for item in logs]
