"""Tests for bots write RBAC toggle."""

import importlib

import pytest


def test_bots_write_protected_by_default(monkeypatch) -> None:
    """Without explicit override, write endpoints require admin dependency."""
    monkeypatch.delenv("JM_API_BOTS_WRITE_ADMIN_ONLY", raising=False)

    import jm_api.api.deps as deps_module
    import jm_api.api.routes.bots as bots_module

    bots_module = importlib.reload(bots_module)

    assert bots_module._write_dependencies == deps_module.ADMIN_ONLY


def test_bots_write_toggle_enables_admin_dependency(monkeypatch) -> None:
    """Truthy toggle keeps admin dependency for write routes."""
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


def test_bots_write_toggle_false_disables_admin_dependency(monkeypatch, caplog) -> None:
    """Setting toggle false disables admin restriction and emits warning."""
    monkeypatch.setenv("JM_API_BOTS_WRITE_ADMIN_ONLY", "false")

    import jm_api.api.routes.bots as bots_module

    with caplog.at_level("WARNING"):
        bots_module = importlib.reload(bots_module)

    assert bots_module._write_dependencies is None
    assert "Bot write protection is DISABLED" in caplog.text


@pytest.mark.parametrize("value", ["0", "no", "off", "FALSE"])
def test_bots_write_toggle_falsey_values_disable_admin_dependency(monkeypatch, value) -> None:
    """Supported falsey values should disable admin-only writes."""
    monkeypatch.setenv("JM_API_BOTS_WRITE_ADMIN_ONLY", value)

    import jm_api.api.routes.bots as bots_module

    bots_module = importlib.reload(bots_module)

    assert bots_module._write_dependencies is None
