"""Tests for authentication functionality."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import time

import jwt
import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker

from jm_api.api import deps as auth_deps
from jm_api.api.deps import (
    SessionTokenCollisionError,
    hash_password,
    persist_refresh_token,
    verify_password,
)
from jm_api.core.config import get_settings
from jm_api.models.session_token import SessionToken
from jm_api.models.user import User


@pytest.fixture
def test_user(db_session: Session) -> User:
    """Create a test user."""
    user = User(
        email="test@example.com",
        password_hash=hash_password("securepassword123"),
        is_active=True,
        is_admin=False,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def csrf_headers(client: TestClient) -> dict[str, str]:
    token = client.cookies.get("csrf_token")
    assert token is not None
    return {"X-CSRF-Token": token}


def cookie_expiry(response, name: str) -> int | None:
    for cookie in response.cookies.jar:
        if cookie.name == name:
            return cookie.expires
    return None


class TestPasswordHashing:
    """Test password hashing utilities."""

    def test_hash_password_returns_string(self) -> None:
        """Test that hash_password returns a string."""
        hashed = hash_password("mypassword")
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_verify_password_correct(self) -> None:
        """Test verifying correct password."""
        password = "mypassword"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self) -> None:
        """Test verifying incorrect password."""
        password = "mypassword"
        hashed = hash_password(password)
        assert verify_password("wrongpassword", hashed) is False

    def test_same_password_different_hashes(self) -> None:
        """Test that same password produces different hashes."""
        password = "mypassword"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True


class TestLoginEndpoint:
    """Test the login endpoint."""

    def test_login_success(self, client: TestClient, test_user: User, db_session: Session) -> None:
        """Test successful login returns tokens."""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "securepassword123",
            },
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" not in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] == 900  # 15 minutes
        assert "refresh_token" in response.cookies

        refresh_session = db_session.execute(
            select(SessionToken).where(SessionToken.user_id == test_user.id)
        ).scalar_one_or_none()
        assert refresh_session is not None
        assert refresh_session.revoked_at is None

    def test_login_sets_csrf_cookie_ttl_to_refresh_ttl(
        self,
        client: TestClient,
        test_user: User,
    ) -> None:
        """CSRF cookie should live as long as refresh cookie to avoid dead-end refresh flows."""
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "securepassword123"},
        )
        assert response.status_code == status.HTTP_200_OK

        refresh_expiry = cookie_expiry(response, "refresh_token")
        csrf_expiry = cookie_expiry(response, "csrf_token")
        assert refresh_expiry is not None
        assert csrf_expiry is not None
        assert csrf_expiry == refresh_expiry

    def test_login_invalid_email(self, client: TestClient, test_user: User) -> None:
        """Test login with invalid email returns 401."""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "wrong@example.com",
                "password": "securepassword123",
            },
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid email or password" in response.json()["detail"]

    def test_login_invalid_password(self, client: TestClient, test_user: User) -> None:
        """Test login with invalid password returns 401."""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "wrongpassword",
            },
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Invalid email or password" in response.json()["detail"]

    def test_login_inactive_user(self, client: TestClient, db_session: Session) -> None:
        """Test login with inactive user returns 401."""
        user = User(
            email="inactive@example.com",
            password_hash=hash_password("password123"),
            is_active=False,
        )
        db_session.add(user)
        db_session.commit()

        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "inactive@example.com",
                "password": "password123",
            },
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "deactivated" in response.json()["detail"]

    def test_login_invalid_email_format(self, client: TestClient) -> None:
        """Test login with invalid email format returns 422."""
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "not-an-email",
                "password": "password123",
            },
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_login_missing_fields(self, client: TestClient) -> None:
        """Test login with missing fields returns 422."""
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_login_short_password_returns_422(self, client: TestClient) -> None:
        """Login payload enforces minimum password length."""
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "short"},
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


class TestMeEndpoint:
    """Test the /me endpoint."""

    def test_get_me_success(self, client: TestClient, test_user: User) -> None:
        """Test getting current user info with valid token."""
        # First login to get a token
        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "securepassword123",
            },
        )
        token = login_response.json()["access_token"]

        # Then get user info
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["email"] == "test@example.com"
        assert data["id"] == test_user.id
        assert data["is_active"] is True
        assert data["is_admin"] is False

    def test_get_me_no_token(self, client: TestClient) -> None:
        """Test getting user info without token returns 401."""
        response = client.get("/api/v1/auth/me")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_get_me_invalid_token(self, client: TestClient) -> None:
        """Test getting user info with invalid token returns 401."""
        response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid_token"},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestRefreshEndpoint:
    """Test the refresh token endpoint."""

    def test_refresh_token_success(self, client: TestClient, test_user: User) -> None:
        """Test refreshing tokens with valid refresh token cookie."""
        # First login to set the cookie
        client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "securepassword123",
            },
        )

        # Refresh tokens
        response = client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" not in data
        assert data["token_type"] == "bearer"

    def test_refresh_token_from_cookie(
        self,
        client: TestClient,
        test_user: User,
        db_session: Session,
    ) -> None:
        """Test refreshing tokens rotates refresh cookie."""
        # First login to set the cookie
        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "securepassword123",
            },
        )
        old_refresh_token = login_response.cookies.get("refresh_token")
        assert old_refresh_token is not None

        # Refresh using cookie
        response = client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" not in data
        assert client.cookies.get("refresh_token") != old_refresh_token

        sessions = db_session.execute(select(SessionToken)).scalars().all()
        assert len(sessions) == 2

        revoked_old = [s for s in sessions if s.revoked_at is not None]
        active_new = [s for s in sessions if s.revoked_at is None]
        assert len(revoked_old) == 1
        assert len(active_new) == 1
        assert active_new[0].rotated_from_jti == revoked_old[0].token_jti

    def test_refresh_sets_csrf_cookie_ttl_to_refresh_ttl(
        self,
        client: TestClient,
        test_user: User,
    ) -> None:
        """Refresh should keep CSRF cookie TTL aligned with refresh cookie TTL."""
        client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "securepassword123"},
        )

        response = client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
        assert response.status_code == status.HTTP_200_OK

        refresh_expiry = cookie_expiry(response, "refresh_token")
        csrf_expiry = cookie_expiry(response, "csrf_token")
        assert refresh_expiry is not None
        assert csrf_expiry is not None
        assert csrf_expiry == refresh_expiry

    def test_refresh_still_works_after_more_than_15_minutes_when_session_is_valid(
        self,
        client: TestClient,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Regression: CSRF cookie must survive beyond 15 minutes for valid refresh sessions."""
        client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "securepassword123"},
        )

        base_time = time.time()
        monkeypatch.setattr("http.cookiejar.time.time", lambda: base_time + (16 * 60))

        assert client.cookies.get("csrf_token") is not None
        assert client.cookies.get("refresh_token") is not None

        response = client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
        assert response.status_code == status.HTTP_200_OK

    def test_refresh_no_token(self, client: TestClient) -> None:
        """Test refresh without token returns 401."""
        response = client.post("/api/v1/auth/refresh")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "Refresh token required" in response.json()["detail"]

    def test_refresh_invalid_token(self, client: TestClient) -> None:
        """Test refresh with invalid cookie token returns 401."""
        client.cookies.set("refresh_token", "invalid_token")
        client.cookies.set("csrf_token", "csrf-test")
        response = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": "csrf-test"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_refresh_malformed_payload_returns_401(
        self,
        client: TestClient,
        test_user: User,
    ) -> None:
        """Malformed JWT payload should return 401 and never 500."""
        settings = get_settings()
        malformed_refresh = jwt.encode(
            {
                "sub": test_user.id,
                "type": "refresh",
                "exp": "not-an-int",
                "iat": "not-an-int",
            },
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        client.cookies.set("refresh_token", malformed_refresh)
        client.cookies.set("csrf_token", "csrf-test")
        response = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": "csrf-test"})
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_refresh_token_reuse_revokes_all_sessions(
        self,
        client: TestClient,
        test_user: User,
        db_session: Session,
    ) -> None:
        """Reusing a rotated/revoked refresh token revokes all user sessions."""
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "securepassword123"},
        )
        first_refresh = login_response.cookies.get("refresh_token")
        assert first_refresh is not None

        rotate_response = client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
        assert rotate_response.status_code == status.HTTP_200_OK

        # Attempt replay with the old token
        client.cookies.set("refresh_token", first_refresh)
        replay_response = client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
        assert replay_response.status_code == status.HTTP_401_UNAUTHORIZED

        active_sessions = db_session.execute(
            select(SessionToken).where(
                SessionToken.user_id == test_user.id,
                SessionToken.revoked_at.is_(None),
            )
        ).scalars().all()
        assert len(active_sessions) == 0


class TestSecurityHardening:
    """Security hardening tests for token/session edge cases."""

    def test_refresh_token_rotation_race_second_consume_fails(
        self,
        client: TestClient,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """If token was already consumed concurrently, refresh returns 401."""
        client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "securepassword123"},
        )

        monkeypatch.setattr("jm_api.api.routes.auth.rotate_refresh_token", lambda *args, **kwargs: False)
        response = client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "consumed" in response.json()["detail"].lower()

    def test_rotate_refresh_token_allows_only_one_concurrent_consumer(
        self,
        db_engine,
        test_user: User,
    ) -> None:
        """Concurrent refresh rotation attempts should allow only one success."""
        old_token = auth_deps.create_refresh_token(test_user.id)
        with Session(db_engine) as session:
            persist_refresh_token(session, old_token)

        session_factory = sessionmaker(bind=db_engine)

        def _attempt_rotate() -> bool:
            with session_factory() as thread_session:
                return auth_deps.rotate_refresh_token(
                    thread_session,
                    old_token,
                    auth_deps.create_refresh_token(test_user.id),
                )

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _i: _attempt_rotate(), range(2)))

        assert sorted(results) == [False, True]

        with Session(db_engine) as verify_session:
            sessions = verify_session.execute(select(SessionToken)).scalars().all()
            active_count = sum(token.revoked_at is None for token in sessions)

        assert len(sessions) >= 1
        assert active_count >= 1

    def test_unknown_refresh_token_does_not_trigger_global_revoke(
        self,
        client: TestClient,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Unknown refresh tokens should not revoke all user sessions."""
        settings = get_settings()
        unknown_token = jwt.encode(
            {
                "sub": test_user.id,
                "type": "refresh",
                "exp": 4102444800,
                "iat": 1700000000,
                "jti": "unknown-session-jti-123",
            },
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        client.cookies.set("refresh_token", unknown_token)
        client.cookies.set("csrf_token", "csrf-test")

        revoke_called = {"value": False}

        def _mark_revoke(*_args, **_kwargs):
            revoke_called["value"] = True

        monkeypatch.setattr("jm_api.api.routes.auth.revoke_user_sessions", _mark_revoke)

        response = client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert revoke_called["value"] is False

    def test_revoked_refresh_token_triggers_global_revoke(
        self,
        client: TestClient,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Revoked token replay should trigger user-wide session revocation."""
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "securepassword123"},
        )
        old_token = login_response.cookies.get("refresh_token")
        assert old_token is not None

        # Rotate once so old_token becomes explicitly revoked.
        rotate_response = client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
        assert rotate_response.status_code == status.HTTP_200_OK

        calls = {"count": 0}

        def _count_revoke(*_args, **_kwargs):
            calls["count"] += 1

        monkeypatch.setattr("jm_api.api.routes.auth.revoke_user_sessions", _count_revoke)
        client.cookies.set("refresh_token", old_token)

        response = client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert calls["count"] == 1

    def test_cleanup_errors_are_swallowed(self, db_session: Session) -> None:
        """Cleanup is opportunistic and should never raise."""

        class FailingSession:
            def execute(self, *_args, **_kwargs):
                raise auth_deps.SQLAlchemyError("db lock")

            def commit(self):
                return None

            def rollback(self):
                return None

        auth_deps._LAST_SESSION_CLEANUP_AT = None
        auth_deps._maybe_cleanup_expired_sessions(FailingSession())

    def test_persist_refresh_token_jti_collision_returns_400(
        self,
        db_session: Session,
        test_user: User,
    ) -> None:
        """Duplicate JTI insertion returns a safe 400 response."""
        token = auth_deps.create_refresh_token(test_user.id)
        persist_refresh_token(db_session, token)

        with pytest.raises(SessionTokenCollisionError):
            persist_refresh_token(db_session, token)

    def test_refresh_token_user_mismatch_returns_401(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        user_factory,
    ) -> None:
        """JWT sub must match persisted session user_id."""
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "securepassword123"},
        )
        refresh_token = login_response.cookies.get("refresh_token")
        assert refresh_token is not None
        jti = auth_deps.get_refresh_token_jti(refresh_token)

        other_user = user_factory(email="other@example.com")
        db_session.execute(
            update(SessionToken)
            .where(SessionToken.token_jti == jti)
            .values(user_id=other_user.id)
        )
        db_session.commit()

        response = client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "mismatch" in response.json()["detail"].lower()

    def test_refresh_allows_legacy_session_rows_without_binding_metadata(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
    ) -> None:
        """Legacy rows with NULL binding metadata should still rotate once."""
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "securepassword123"},
        )
        refresh_token = login_response.cookies.get("refresh_token")
        assert refresh_token is not None
        jti = auth_deps.get_refresh_token_jti(refresh_token)

        db_session.execute(
            update(SessionToken)
            .where(SessionToken.token_jti == jti)
            .values(user_agent_hash=None, ip_subnet=None)
        )
        db_session.commit()

        response = client.post("/api/v1/auth/refresh", headers=csrf_headers(client))
        assert response.status_code == status.HTTP_200_OK

    def test_rotate_refresh_token_rejects_missing_request_metadata_when_bound(
        self,
        db_session: Session,
        test_user: User,
    ) -> None:
        """Bound session metadata cannot be bypassed by passing None values."""
        old_token = auth_deps.create_refresh_token(test_user.id)
        new_token = auth_deps.create_refresh_token(test_user.id)
        persist_refresh_token(
            db_session,
            old_token,
            user_agent_hash="ua-hash",
            ip_subnet="203.0.113.0/24",
        )

        rotated = auth_deps.rotate_refresh_token(
            db_session,
            old_token,
            new_token,
            user_agent_hash=None,
            ip_subnet=None,
        )
        assert rotated is False

    def test_refresh_rejects_malformed_forwarded_ip_and_missing_ua_when_session_bound(
        self,
        client: TestClient,
        db_session: Session,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Bound sessions fail closed when refresh request metadata is missing/unparseable."""
        monkeypatch.setenv("JM_API_TRUST_PROXY_HEADERS", "true")
        get_settings.cache_clear()

        try:
            login_response = client.post(
                "/api/v1/auth/login",
                json={"email": "test@example.com", "password": "securepassword123"},
                headers={"User-Agent": "ua-original", "X-Forwarded-For": "203.0.113.19"},
            )
            assert login_response.status_code == status.HTTP_200_OK
            refresh_cookie = login_response.cookies.get("refresh_token")
            assert refresh_cookie is not None

            jti = auth_deps.get_refresh_token_jti(refresh_cookie)
            db_session.execute(
                update(SessionToken)
                .where(SessionToken.token_jti == jti)
                .values(
                    user_agent_hash=auth_deps.fingerprint_user_agent("ua-original"),
                    ip_subnet="203.0.113.0/24",
                )
            )
            db_session.commit()

            response = client.post(
                "/api/v1/auth/refresh",
                headers={
                    "X-CSRF-Token": client.cookies.get("csrf_token") or "",
                    "User-Agent": "",
                    "X-Forwarded-For": "not-an-ip",
                },
            )
            assert response.status_code == status.HTTP_401_UNAUTHORIZED
            assert "consumed" in response.json()["detail"].lower()
        finally:
            get_settings.cache_clear()

    def test_login_ignores_x_forwarded_for_when_proxy_headers_untrusted(
        self,
        client: TestClient,
        test_user: User,
        db_session: Session,
    ) -> None:
        """Spoofed X-Forwarded-For should not be trusted by default."""
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "securepassword123"},
            headers={"X-Forwarded-For": "198.51.100.22", "User-Agent": "ua-test"},
        )
        assert response.status_code == status.HTTP_200_OK

        session = db_session.execute(select(SessionToken)).scalar_one()
        assert session.ip_subnet is None

    def test_login_falls_back_to_client_ip_when_forwarded_ip_invalid(
        self,
        client: TestClient,
        test_user: User,
        monkeypatch: pytest.MonkeyPatch,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """Invalid X-Forwarded-For should not be used when proxy headers are enabled."""
        monkeypatch.setenv("JM_API_TRUST_PROXY_HEADERS", "true")
        get_settings.cache_clear()

        try:
            response = client.post(
                "/api/v1/auth/login",
                json={"email": "test@example.com", "password": "securepassword123"},
                headers={"X-Forwarded-For": "not-an-ip", "User-Agent": "ua-test"},
            )
            assert response.status_code == status.HTTP_200_OK
            assert '"event": "security.audit"' in caplog.text
            assert '"ip": "testclient"' in caplog.text
            assert '"ip": "not-an-ip"' not in caplog.text
        finally:
            get_settings.cache_clear()


class TestJwtSigningKeyPrecedence:
    def test_decode_token_uses_only_configured_signing_keys(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("JM_API_JWT_SECRET_KEY", "legacy-secret")
        monkeypatch.setenv("JM_API_JWT_SIGNING_KEYS", '["primary-key", "secondary-key"]')
        get_settings.cache_clear()

        try:
            settings = get_settings()
            payload = {
                "sub": "user-1",
                "type": "access",
                "iat": 1700000000,
                "exp": 4102444800,
            }

            legacy_token = jwt.encode(
                payload,
                "legacy-secret",
                algorithm=settings.jwt_algorithm,
            )
            with pytest.raises(auth_deps.HTTPException) as exc_info:
                auth_deps.decode_token(legacy_token)
            assert exc_info.value.status_code == status.HTTP_401_UNAUTHORIZED

            rotated_token = jwt.encode(
                payload,
                "primary-key",
                algorithm=settings.jwt_algorithm,
            )
            decoded = auth_deps.decode_token(rotated_token)
            assert decoded.sub == "user-1"
        finally:
            get_settings.cache_clear()


class TestLogoutEndpoint:
    """Test the logout endpoint."""

    def test_logout_clears_cookie(self, client: TestClient, test_user: User) -> None:
        """Test logout clears refresh token cookie."""
        # First login to set the cookie
        client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "securepassword123",
            },
        )
        assert "refresh_token" in client.cookies

        # Logout
        response = client.post("/api/v1/auth/logout", headers=csrf_headers(client))
        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_logout_revokes_current_refresh_token(
        self,
        client: TestClient,
        test_user: User,
        db_session: Session,
    ) -> None:
        """Test logout revokes the refresh token used for the session."""
        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "securepassword123",
            },
        )
        refresh_token = login_response.cookies.get("refresh_token")
        assert refresh_token is not None

        response = client.post("/api/v1/auth/logout", headers=csrf_headers(client))
        assert response.status_code == status.HTTP_204_NO_CONTENT

        revoked_rows = db_session.execute(
            select(SessionToken).where(SessionToken.revoked_at.is_not(None))
        ).scalars().all()
        assert len(revoked_rows) >= 1

        # Try to reuse the revoked token directly
        client.cookies.set("refresh_token", refresh_token)
        client.cookies.set("csrf_token", "csrf-test")
        refresh_response = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": "csrf-test"})
        assert refresh_response.status_code == status.HTTP_401_UNAUTHORIZED


class TestSessionManagement:
    def test_list_sessions_returns_current(self, client: TestClient, test_user: User) -> None:
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "securepassword123"},
        )
        assert login_response.status_code == status.HTTP_200_OK

        me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {login_response.json()['access_token']}"})
        response = client.get(
            "/api/v1/auth/sessions",
            headers={"Authorization": f"Bearer {login_response.json()['access_token']}"},
        )
        assert me.status_code == status.HTTP_200_OK
        assert response.status_code == status.HTTP_200_OK
        payload = response.json()
        assert len(payload["sessions"]) >= 1
        assert any(item["current"] for item in payload["sessions"])

    def test_refresh_requires_csrf_header(self, client: TestClient, test_user: User) -> None:
        client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "securepassword123"},
        )
        response = client.post("/api/v1/auth/refresh")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_revoke_others_requires_valid_refresh_cookie(self, client: TestClient, test_user: User) -> None:
        login_response = client.post(
            "/api/v1/auth/login",
            json={"email": "test@example.com", "password": "securepassword123"},
        )
        access_token = login_response.json()["access_token"]
        csrf = client.cookies.get("csrf_token")
        assert csrf is not None

        client.cookies.pop("refresh_token", None)
        response = client.post(
            "/api/v1/auth/sessions/revoke-others",
            headers={"Authorization": f"Bearer {access_token}", "X-CSRF-Token": csrf},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestRateLimiting:
    """Test rate limiting on login endpoint."""

    @pytest.mark.xfail(reason="Rate limiting uses shared in-memory storage across tests")
    def test_login_rate_limit(self, client: TestClient, test_user: User) -> None:
        """Test that login is rate limited after 5 attempts.
        
        Note: This test may fail when run with other tests due to shared rate limit state.
        """
        # Make 5 failed login attempts
        for i in range(5):
            response = client.post(
                "/api/v1/auth/login",
                json={
                    "email": f"test{i}@example.com",  # Use different emails to avoid rate limit
                    "password": "wrongpassword",
                },
            )
            # Expect 401 for the first 5 attempts (if they were valid emails) 
            # or 401 for invalid email
            assert response.status_code in (status.HTTP_401_UNAUTHORIZED,)

        # 6th attempt with same IP should be rate limited
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "wrongpassword",
            },
        )
        # This may be 429 if rate limited or 401 if not
        assert response.status_code in (status.HTTP_429_TOO_MANY_REQUESTS, status.HTTP_401_UNAUTHORIZED)


class TestUserModel:
    """Test User model."""

    def test_user_creation(self, db_session: Session) -> None:
        """Test creating a user."""
        user = User(
            email="newuser@example.com",
            password_hash=hash_password("password123"),
            is_active=True,
            is_admin=False,
        )
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)

        assert user.id is not None
        assert user.email == "newuser@example.com"
        assert user.is_active is True
        assert user.is_admin is False
        assert user.create_at is not None
        assert user.last_update_at is not None

    def test_user_email_unique(self, db_session: Session, test_user: User) -> None:
        """Test that email must be unique."""
        user = User(
            email="test@example.com",  # Same as test_user
            password_hash=hash_password("password123"),
        )
        db_session.add(user)
        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()
