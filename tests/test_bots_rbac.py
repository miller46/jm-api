"""Tests for optional bots write RBAC toggle."""

import importlib

from fastapi import status
from fastapi.testclient import TestClient


def test_bots_write_open_by_default(client: TestClient) -> None:
    """Without toggle, write endpoints remain backward compatible."""
    response = client.post("/api/v1/bots", json={"rig_id": "rig-new"})
    assert response.status_code == status.HTTP_201_CREATED


def test_bots_write_toggle_enables_admin_dependency(monkeypatch) -> None:
    """Enabling toggle wires admin dependency for write routes."""
    monkeypatch.setenv("JM_API_BOTS_WRITE_ADMIN_ONLY", "true")

    import jm_api.api.deps as deps_module
    import jm_api.api.routes.bots as bots_module

    bots_module = importlib.reload(bots_module)

    assert bots_module._write_dependencies == deps_module.ADMIN_ONLY


def test_bots_write_toggle_handles_whitespace_truthy_value(monkeypatch) -> None:
    """Toggle parser should treat trimmed truthy values as enabled."""
    monkeypatch.setenv("JM_API_BOTS_WRITE_ADMIN_ONLY", "  TrUe  ")

    import jm_api.api.deps as deps_module
    import jm_api.api.routes.bots as bots_module

    bots_module = importlib.reload(bots_module)

    assert bots_module._write_dependencies == deps_module.ADMIN_ONLY
