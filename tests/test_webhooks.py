from __future__ import annotations

import json

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from jm_api.models.webhook import Webhook, WebhookDeliveryLog
from jm_api.services import webhooks as webhook_service


def test_webhook_crud_endpoints(client, user_headers) -> None:
    create_response = client.post(
        "/api/v1/webhooks",
        headers=user_headers,
        json={
            "target_url": "https://example.com/webhook",
            "event_types": ["bot.created", "bot.updated"],
            "secret": "supersecret",
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["target_url"] == "https://example.com/webhook"
    assert created["event_types"] == ["bot.created", "bot.updated"]

    list_response = client.get("/api/v1/webhooks", headers=user_headers)
    assert list_response.status_code == 200
    listed = list_response.json()
    assert len(listed) == 1
    webhook_id = listed[0]["id"]

    update_response = client.patch(
        f"/api/v1/webhooks/{webhook_id}",
        headers=user_headers,
        json={"event_types": ["bot.deleted"], "secret": "rotated-secret"},
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["event_types"] == ["bot.deleted"]

    delete_response = client.delete(f"/api/v1/webhooks/{webhook_id}", headers=user_headers)
    assert delete_response.status_code == 204

    final_list = client.get("/api/v1/webhooks", headers=user_headers)
    assert final_list.status_code == 200
    assert final_list.json() == []


def test_create_webhook_rejects_internal_url(client, user_headers) -> None:
    response = client.post(
        "/api/v1/webhooks",
        headers=user_headers,
        json={
            "target_url": "http://localhost/hook",
            "event_types": ["bot.created"],
            "secret": "supersecret",
        },
    )
    assert response.status_code == 400
    assert "local/internal" in response.json()["detail"]


def test_delivery_logs_endpoint_returns_entries(client, user_headers, db_session: Session) -> None:
    created = client.post(
        "/api/v1/webhooks",
        headers=user_headers,
        json={
            "target_url": "https://example.com/webhook",
            "event_types": ["bot.created"],
            "secret": "supersecret",
        },
    ).json()

    db_session.add(
        WebhookDeliveryLog(
            id="a" * 32,
            webhook_id=created["id"],
            event_id="evt_123",
            event_type="bot.created",
            success=True,
            attempts=1,
            status_code=200,
            response_body="ok",
            error_message=None,
        )
    )
    db_session.commit()

    resp = client.get(f"/api/v1/webhooks/{created['id']}/deliveries", headers=user_headers)
    assert resp.status_code == 200
    payload = resp.json()
    assert len(payload) == 1
    assert payload[0]["event_type"] == "bot.created"


def test_deliver_event_records_success_log(monkeypatch: pytest.MonkeyPatch, db_session: Session, user_factory) -> None:
    user = user_factory(email="deliver@example.com")
    webhook = Webhook(
        user_id=user.id,
        target_url="https://example.com/hook",
        event_types=["bot.created"],
        secret="supersecret",
    )
    db_session.add(webhook)
    db_session.commit()

    captured: dict[str, object] = {}

    class _Response:
        status_code = 200
        text = "ok"

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

        def post(self, url: str, *, content: bytes, headers: dict[str, str]):
            captured["url"] = url
            captured["content"] = content
            captured["headers"] = headers
            return _Response()

    monkeypatch.setattr(webhook_service, "MAX_RETRIES", 1)
    monkeypatch.setattr(webhook_service.httpx, "Client", _Client)

    webhook_service.deliver_event(db_session, event_type="bot.created", data={"id": "bot_1"})

    logs = db_session.execute(select(WebhookDeliveryLog)).scalars().all()
    assert len(logs) == 1
    assert logs[0].success is True
    assert logs[0].status_code == 200

    body = json.loads(captured["content"])
    assert body["type"] == "bot.created"
    assert body["data"]["id"] == "bot_1"

    headers = captured["headers"]
    assert headers["X-Webhook-Signature"].startswith("sha256=")
