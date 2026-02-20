"""Authentication dependencies and utilities."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from hashlib import sha256
from ipaddress import ip_address
from uuid import uuid4

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import ValidationError
from sqlalchemy import delete, or_, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from jm_api.core.config import get_settings
from jm_api.db.session import get_db
from jm_api.models.session_token import SessionToken
from jm_api.models.user import User
from jm_api.schemas.auth import TokenPayload

security = HTTPBearer(auto_error=False)

_LAST_SESSION_CLEANUP_AT: datetime | None = None


class RefreshTokenState(str, Enum):
    """Refresh-token lifecycle state in persistent session store."""

    ACTIVE = "active"
    REVOKED = "revoked"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


class SessionTokenCollisionError(Exception):
    """Raised when a refresh token JTI collides in persistent storage."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _get_signing_keys() -> list[str]:
    settings = get_settings()
    keys = [key for key in settings.jwt_signing_keys if key]
    if not keys:
        keys = [settings.jwt_secret_key]
    elif settings.jwt_secret_key not in keys:
        keys.append(settings.jwt_secret_key)
    return keys


def fingerprint_user_agent(user_agent: str | None) -> str | None:
    if not user_agent:
        return None
    return sha256(user_agent.encode("utf-8")).hexdigest()


def ip_to_subnet(ip: str | None) -> str | None:
    if not ip:
        return None
    try:
        parsed = ip_address(ip)
    except ValueError:
        return None

    if parsed.version == 4:
        octets = str(parsed).split(".")
        return ".".join(octets[:3]) + ".0/24"

    hextets = parsed.exploded.split(":")
    return ":".join(hextets[:4]) + "::/64"


def _maybe_cleanup_expired_sessions(db: Session) -> None:
    """Opportunistically cleanup expired session rows at a bounded interval."""
    global _LAST_SESSION_CLEANUP_AT

    settings = get_settings()
    now = _utcnow()
    if _LAST_SESSION_CLEANUP_AT is not None:
        elapsed = (now - _LAST_SESSION_CLEANUP_AT).total_seconds()
        if elapsed < settings.session_cleanup_interval_seconds:
            return

    try:
        db.execute(delete(SessionToken).where(SessionToken.expires_at <= now))
        db.commit()
        _LAST_SESSION_CLEANUP_AT = now
    except Exception:
        db.rollback()


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
        _get_signing_keys()[0],
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
        _get_signing_keys()[0],
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str) -> TokenPayload:
    """Decode and validate a JWT token."""
    settings = get_settings()

    last_error: Exception | None = None
    for key in _get_signing_keys():
        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=[settings.jwt_algorithm],
            )
            return TokenPayload(**payload)
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except (jwt.InvalidTokenError, ValidationError) as exc:
            last_error = exc
            continue

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid token",
        headers={"WWW-Authenticate": "Bearer"},
    ) from last_error


def _decode_refresh_token_payload(token: str) -> TokenPayload:
    payload = decode_token(token)
    if payload.type != "refresh" or payload.jti is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload


def persist_refresh_token(
    db: Session,
    token: str,
    rotated_from_jti: str | None = None,
    user_agent_hash: str | None = None,
    ip_subnet: str | None = None,
) -> None:
    """Persist issued refresh token in session store."""
    payload = _decode_refresh_token_payload(token)
    issued_at = datetime.fromtimestamp(payload.iat, tz=timezone.utc)
    expires_at = datetime.fromtimestamp(payload.exp, tz=timezone.utc)

    db.add(
        SessionToken(
            token_jti=payload.jti,
            user_id=payload.sub,
            issued_at=issued_at,
            expires_at=expires_at,
            revoked_at=None,
            rotated_from_jti=rotated_from_jti,
            user_agent_hash=user_agent_hash,
            ip_subnet=ip_subnet,
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise SessionTokenCollisionError from exc
    except SQLAlchemyError:
        db.rollback()
        raise


def rotate_refresh_token(
    db: Session,
    old_token: str,
    new_token: str,
    user_agent_hash: str | None = None,
    ip_subnet: str | None = None,
) -> bool:
    """Atomically consume old refresh token and persist a new replacement token."""
    old_payload = _decode_refresh_token_payload(old_token)
    new_payload = _decode_refresh_token_payload(new_token)

    issued_at = datetime.fromtimestamp(new_payload.iat, tz=timezone.utc)
    expires_at = datetime.fromtimestamp(new_payload.exp, tz=timezone.utc)

    try:
        query = (
            update(SessionToken)
            .where(SessionToken.token_jti == old_payload.jti)
            .where(SessionToken.revoked_at.is_(None))
        )
        if user_agent_hash is not None:
            query = query.where(
                or_(
                    SessionToken.user_agent_hash == user_agent_hash,
                    SessionToken.user_agent_hash.is_(None),
                )
            )
        if ip_subnet is not None:
            query = query.where(
                or_(
                    SessionToken.ip_subnet == ip_subnet,
                    SessionToken.ip_subnet.is_(None),
                )
            )

        result = db.execute(query.values(revoked_at=_utcnow()))

        if not result.rowcount:
            db.rollback()
            return False

        db.add(
            SessionToken(
                token_jti=new_payload.jti,
                user_id=new_payload.sub,
                issued_at=issued_at,
                expires_at=expires_at,
                revoked_at=None,
                rotated_from_jti=old_payload.jti,
                user_agent_hash=user_agent_hash,
                ip_subnet=ip_subnet,
            )
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise SessionTokenCollisionError from exc
    except SQLAlchemyError:
        db.rollback()
        raise

    return True


def revoke_refresh_token(db: Session, token: str) -> None:
    """Mark refresh token as revoked in persistent store."""
    try:
        payload = _decode_refresh_token_payload(token)
    except HTTPException:
        return

    now = _utcnow()
    try:
        db.execute(
            update(SessionToken)
            .where(SessionToken.token_jti == payload.jti)
            .values(revoked_at=now)
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def revoke_user_sessions(db: Session, user_id: str) -> None:
    """Revoke all active refresh sessions for a user (token-reuse hardening)."""
    now = _utcnow()
    try:
        db.execute(
            update(SessionToken)
            .where(SessionToken.user_id == user_id)
            .where(SessionToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise


def consume_refresh_token(db: Session, token: str) -> bool:
    """Atomically consume (revoke) an active refresh token once."""
    try:
        payload = _decode_refresh_token_payload(token)
    except HTTPException:
        return False

    now = _utcnow()

    try:
        result = db.execute(
            update(SessionToken)
            .where(SessionToken.token_jti == payload.jti)
            .where(SessionToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        raise

    return bool(result.rowcount)


def get_refresh_token_state(db: Session, token: str) -> RefreshTokenState:
    """Inspect refresh token state in session store."""
    payload = _decode_refresh_token_payload(token)
    _maybe_cleanup_expired_sessions(db)

    session_token = db.execute(
        select(SessionToken).where(SessionToken.token_jti == payload.jti)
    ).scalar_one_or_none()

    if session_token is None:
        return RefreshTokenState.UNKNOWN

    if session_token.user_id != payload.sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token mismatch",
            headers={"WWW-Authenticate": "Bearer"},
        )

    now = _utcnow()
    if _normalize_utc(session_token.expires_at) <= now:
        return RefreshTokenState.EXPIRED

    if session_token.revoked_at is not None:
        return RefreshTokenState.REVOKED

    return RefreshTokenState.ACTIVE


def is_refresh_token_revoked(db: Session, token: str) -> bool:
    """Backward-compatible revocation check."""
    return get_refresh_token_state(db, token) != RefreshTokenState.ACTIVE


def get_refresh_token_jti(token: str) -> str:
    """Get refresh token JTI."""
    payload = _decode_refresh_token_payload(token)
    assert payload.jti is not None
    return payload.jti


def list_user_sessions(db: Session, user_id: str) -> list[SessionToken]:
    return db.execute(
        select(SessionToken)
        .where(SessionToken.user_id == user_id)
        .order_by(SessionToken.issued_at.desc())
    ).scalars().all()


def revoke_session_by_jti(db: Session, user_id: str, token_jti: str) -> bool:
    result = db.execute(
        update(SessionToken)
        .where(SessionToken.user_id == user_id)
        .where(SessionToken.token_jti == token_jti)
        .where(SessionToken.revoked_at.is_(None))
        .values(revoked_at=_utcnow())
    )
    db.commit()
    return bool(result.rowcount)


def revoke_other_sessions(db: Session, user_id: str, current_jti: str | None) -> int:
    query = (
        update(SessionToken)
        .where(SessionToken.user_id == user_id)
        .where(SessionToken.revoked_at.is_(None))
    )
    if current_jti:
        query = query.where(SessionToken.token_jti != current_jti)
    result = db.execute(query.values(revoked_at=_utcnow()))
    db.commit()
    return int(result.rowcount or 0)


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
