from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import socket
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from jm_api.db.base import generate_id
from jm_api.models.webhook import Webhook, WebhookDeliveryLog

MAX_RETRIES = 5


def validate_webhook_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Webhook URL must be http or https")
    if not parsed.hostname:
        raise ValueError("Webhook URL host is required")

    hostname = parsed.hostname.lower()
    if hostname in {"localhost", "0.0.0.0"} or hostname.endswith(".local"):
        raise ValueError("Webhook URL points to a local/internal address")

    try:
        ip = ipaddress.ip_address(hostname)
    except ValueError:
        ip = None

    if ip is not None and (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved):
        raise ValueError("Webhook URL points to a private/internal IP")

    try:
        addrs = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return

    for addr in addrs:
        raw_ip = addr[4][0]
        try:
            parsed_ip = ipaddress.ip_address(raw_ip)
        except ValueError:
            continue
        if parsed_ip.is_private or parsed_ip.is_loopback or parsed_ip.is_link_local or parsed_ip.is_reserved:
            raise ValueError("Webhook URL resolves to a private/internal IP")


def _signature(secret: str, payload: bytes) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def deliver_event(db: Session, *, event_type: str, data: dict) -> None:
    webhooks = db.execute(
        select(Webhook).where(Webhook.is_active.is_(True))
    ).scalars().all()

    event_id = f"evt_{generate_id()[:16]}"
    payload_obj = {
        "id": event_id,
        "type": event_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "idempotency_key": event_id,
        "data": data,
    }
    payload = json.dumps(payload_obj).encode("utf-8")

    with httpx.Client(timeout=5.0) as client:
        for wh in webhooks:
            if event_type not in (wh.event_types or []):
                continue

            attempts = 0
            success = False
            status_code: int | None = None
            response_body: str | None = None
            error_message: str | None = None

            while attempts < MAX_RETRIES and not success:
                attempts += 1
                try:
                    resp = client.post(
                        wh.target_url,
                        content=payload,
                        headers={
                            "Content-Type": "application/json",
                            "X-Webhook-Signature": _signature(wh.secret, payload),
                            "X-Webhook-Event": event_type,
                            "X-Webhook-Delivery": event_id,
                        },
                    )
                    status_code = resp.status_code
                    response_body = resp.text[:1000]
                    success = 200 <= resp.status_code < 300
                    if not success and attempts < MAX_RETRIES:
                        time.sleep(2 ** (attempts - 1))
                except Exception as exc:  # noqa: BLE001
                    error_message = str(exc)
                    if attempts < MAX_RETRIES:
                        time.sleep(2 ** (attempts - 1))

            db.add(
                WebhookDeliveryLog(
                    id=generate_id(),
                    webhook_id=wh.id,
                    event_id=event_id,
                    event_type=event_type,
                    success=success,
                    attempts=attempts,
                    status_code=status_code,
                    response_body=response_body,
                    error_message=error_message,
                )
            )

    db.commit()
