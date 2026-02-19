"""Authentication dependencies and utilities."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from jm_api.core.config import get_settings
from jm_api.db.session import get_db
from jm_api.models.session_token import SessionToken
from jm_api.models.user import User
from jm_api.schemas.auth import TokenPayload

security = HTTPBearer(auto_error=False)

_LAST_SESSION_CLEANUP_AT: datetime | None = None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _maybe_cleanup_expired_sessions(db: Session) -> None:
    """Opportunistically cleanup expired session rows at a bounded interval."""
    global _LAST_SESSION_CLEANUP_AT

    settings = get_settings()
    now = _utcnow()
    if _LAST_SESSION_CLEANUP_AT is not None:
        elapsed = (now - _LAST_SESSION_CLEANUP_AT).total_seconds()
        if elapsed < settings.session_cleanup_interval_seconds:
            return

    db.execute(delete(SessionToken).where(SessionToken.expires_at <= now))
    db.commit()
    _LAST_SESSION_CLEANUP_AT = now


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    password_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_bytes)


def create_access_token(user_id: str, expires_delta: timedelta | None = None) -> str:
    """Create a JWT access token."""
    settings = get_settings()

    if expires_delta is None:
        expires_delta = timedelta(minutes=settings.jwt_access_token_expire_minutes)

    now = _utcnow()
    expire = now + expires_delta

    payload = {
        "sub": user_id,
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
        "type": "access",
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def create_refresh_token(user_id: str) -> str:
    """Create a JWT refresh token."""
    settings = get_settings()

    now = _utcnow()
    expire = now + timedelta(days=settings.jwt_refresh_token_expire_days)

    payload = {
        "sub": user_id,
        "exp": int(expire.timestamp()),
        "iat": int(now.timestamp()),
        "jti": str(uuid4()),
        "type": "refresh",
    }

    return jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> TokenPayload:
    """Decode and validate a JWT token."""
    settings = get_settings()

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        return TokenPayload(**payload)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _decode_refresh_token_payload(token: str) -> TokenPayload:
    payload = decode_token(token)
    if payload.type != "refresh" or payload.jti is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def persist_refresh_token(db: Session, token: str, rotated_from_jti: str | None = None) -> None:
    """Persist issued refresh token in session store."""
    payload = _decode_refresh_token_payload(token)
    issued_at = datetime.fromtimestamp(payload.iat, tz=timezone.utc)
    expires_at = datetime.fromtimestamp(payload.exp, tz=timezone.utc)

    existing = db.execute(
        select(SessionToken).where(SessionToken.token_jti == payload.jti)
    ).scalar_one_or_none()
    if existing is None:
        db.add(
            SessionToken(
                token_jti=payload.jti,
                user_id=payload.sub,
                issued_at=issued_at,
                expires_at=expires_at,
                revoked_at=None,
                rotated_from_jti=rotated_from_jti,
            )
        )
        db.commit()


def revoke_refresh_token(db: Session, token: str) -> None:
    """Mark refresh token as revoked in persistent store."""
    try:
        payload = _decode_refresh_token_payload(token)
    except HTTPException:
        return

    now = _utcnow()
    db.execute(
        update(SessionToken)
        .where(SessionToken.token_jti == payload.jti)
        .values(revoked_at=now)
    )
    db.commit()


def is_refresh_token_revoked(db: Session, token: str) -> bool:
    """Check whether a refresh token is revoked or unknown in persistent store."""
    payload = _decode_refresh_token_payload(token)
    _maybe_cleanup_expired_sessions(db)

    session_token = db.execute(
        select(SessionToken).where(SessionToken.token_jti == payload.jti)
    ).scalar_one_or_none()

    if session_token is None:
        return True

    now = _utcnow()
    if _normalize_utc(session_token.expires_at) <= now:
        return True

    return session_token.revoked_at is not None


def get_refresh_token_jti(token: str) -> str:
    """Get refresh token JTI."""
    payload = _decode_refresh_token_payload(token)
    assert payload.jti is not None
    return payload.jti


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    """Get the current authenticated user from the request."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_payload = decode_token(credentials.credentials)

    if token_payload.type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.execute(
        select(User).where(User.id == token_payload.sub)
    ).scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


get_current_active_user = get_current_user

def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    """Require the current user to have admin privileges."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


require_auth = get_current_active_user
ADMIN_ONLY = [Depends(require_admin)]
