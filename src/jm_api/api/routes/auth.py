"""Authentication routes."""

from __future__ import annotations

import structlog
from secrets import token_urlsafe

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from jm_api.api.deps import (
    RefreshTokenState,
    SessionTokenCollisionError,
    create_access_token,
    create_refresh_token,
    decode_token,
    fingerprint_user_agent,
    get_current_user,
    get_refresh_token_jti,
    get_refresh_token_state,
    hash_password,
    ip_to_subnet,
    list_user_sessions,
    persist_refresh_token,
    revoke_other_sessions,
    revoke_refresh_token,
    revoke_session_by_jti,
    revoke_user_sessions,
    rotate_refresh_token,
    verify_password,
)
from jm_api.core.config import get_settings
from jm_api.db.session import get_db
from jm_api.models.user import User
from jm_api.schemas.auth import (
    LoginRequest,
    SessionInfo,
    SessionListResponse,
    TokenResponse,
    UserCreate,
    UserResponse,
)

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/auth", tags=["authentication"])
logger = structlog.get_logger(__name__)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _client_ip(request: Request) -> str | None:
    settings = get_settings()
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _set_auth_cookies(response: Response, refresh_token: str, csrf_token: str) -> None:
    settings = get_settings()
    secure_cookie = settings.environment in {"production", "staging"}
    ttl = settings.jwt_refresh_token_expire_days * 24 * 60 * 60
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        max_age=ttl,
    )
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=secure_cookie,
        samesite="lax",
        max_age=ttl,
    )


def _validate_csrf(csrf_cookie: str | None, csrf_header: str | None) -> None:
    if not csrf_cookie or not csrf_header or csrf_cookie != csrf_header:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="CSRF validation failed")


def _audit(request: Request, event_type: str, outcome: str, **extra: object) -> None:
    logger.info(
        "security.audit",
        event_type=event_type,
        outcome=outcome,
        user_agent=request.headers.get("user-agent"),
        ip=_client_ip(request),
        request_id=_request_id(request),
        risk_flags=extra.pop("risk_flags", []),
        **extra,
    )


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5 per 15 minutes")
def login(
    request: Request,
    login_data: LoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Authenticate user and return JWT tokens.

    Rate limited to 5 attempts per 15 minutes per IP address.
    """
    user = db.execute(select(User).where(User.email == login_data.email)).scalar_one_or_none()

    if user is None or not verify_password(login_data.password, user.password_hash):
        logger.warning(
            "auth.login.failed",
            reason="invalid_credentials",
            email=login_data.email,
            request_id=_request_id(request),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        logger.warning(
            "auth.login.failed",
            reason="user_inactive",
            email=login_data.email,
            request_id=_request_id(request),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    user_agent_hash = fingerprint_user_agent(request.headers.get("user-agent"))
    ip_subnet = ip_to_subnet(_client_ip(request))
    try:
        persist_refresh_token(
            db,
            refresh_token,
            user_agent_hash=user_agent_hash,
            ip_subnet=ip_subnet,
        )
    except SessionTokenCollisionError:
        logger.warning(
            "auth.login.failed",
            reason="session_token_collision",
            user_id=user.id,
            request_id=_request_id(request),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to establish session",
        )
    except SQLAlchemyError:
        logger.exception(
            "auth.login.failed",
            reason="session_persist_error",
            user_id=user.id,
            request_id=_request_id(request),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service unavailable",
        )

    settings = get_settings()
    csrf_token = token_urlsafe(32)
    logger.info(
        "auth.login.success",
        user_id=user.id,
        email=user.email,
        request_id=_request_id(request),
    )
    _audit(request, "auth.login", "success", user_id=user.id)
    _set_auth_cookies(response, refresh_token, csrf_token)
    response.headers["X-CSRF-Token"] = csrf_token

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5 per 15 minutes")
def signup(
    request: Request,
    user_data: UserCreate,
    db: Session = Depends(get_db),
) -> User:
    """Register a new user.

    Rate limited to 5 attempts per 15 minutes per IP address.
    """
    # Check if user already exists
    existing_user = db.execute(
        select(User).where(User.email == user_data.email)
    ).scalar_one_or_none()

    if existing_user is not None:
        logger.warning(
            "auth.signup.failed",
            reason="email_exists",
            email=user_data.email,
            request_id=_request_id(request),
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    # Create new user
    password_hash = hash_password(user_data.password)
    new_user = User(
        email=user_data.email,
        password_hash=password_hash,
        is_active=True,
        is_admin=False,
    )

    db.add(new_user)
    try:
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.exception(
            "auth.signup.failed",
            reason="database_error",
            email=user_data.email,
            request_id=_request_id(request),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to create user",
        )
    db.refresh(new_user)

    logger.info(
        "auth.signup.success",
        user_id=new_user.id,
        email=new_user.email,
        request_id=_request_id(request),
    )

    return new_user


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(
    request: Request,
    response: Response,
    refresh_token_cookie: str | None = Cookie(None, alias="refresh_token"),
    csrf_cookie: str | None = Cookie(None, alias="csrf_token"),
    x_csrf_token: str | None = Header(None, alias="X-CSRF-Token"),
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Refresh access token using the httpOnly refresh-token cookie."""
    token = refresh_token_cookie

    if token is None:
        logger.warning(
            "auth.refresh.failed",
            reason="missing_refresh_cookie",
            request_id=_request_id(request),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _validate_csrf(csrf_cookie, x_csrf_token)

    try:
        refresh_state = get_refresh_token_state(db, token)
    except SQLAlchemyError:
        logger.exception(
            "auth.refresh.failed",
            reason="session_lookup_error",
            request_id=_request_id(request),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service unavailable",
        )

    if refresh_state != RefreshTokenState.ACTIVE:
        if refresh_state == RefreshTokenState.REVOKED:
            # Token replay hardening only on explicit revoked/reuse signal.
            try:
                revoked_payload = decode_token(token)
                if revoked_payload.type == "refresh":
                    revoke_user_sessions(db, revoked_payload.sub)
            except (HTTPException, SQLAlchemyError):
                logger.exception(
                    "auth.refresh.failed",
                    reason="replay_containment_error",
                    request_id=_request_id(request),
                )

        logger.warning(
            "auth.refresh.failed",
            reason=f"refresh_token_{refresh_state.value}",
            request_id=_request_id(request),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_payload = decode_token(token)

    if token_payload.type != "refresh":
        logger.warning(
            "auth.refresh.failed",
            reason="invalid_token_type",
            token_type=token_payload.type,
            request_id=_request_id(request),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.execute(select(User).where(User.id == token_payload.sub)).scalar_one_or_none()

    if user is None:
        logger.warning(
            "auth.refresh.failed",
            reason="user_not_found",
            user_id=token_payload.sub,
            request_id=_request_id(request),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        logger.warning(
            "auth.refresh.failed",
            reason="user_inactive",
            user_id=user.id,
            request_id=_request_id(request),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_settings()
    new_access_token = create_access_token(user.id)
    new_refresh_token = create_refresh_token(user.id)
    user_agent_hash = fingerprint_user_agent(request.headers.get("user-agent"))
    ip_subnet = ip_to_subnet(_client_ip(request))
    try:
        rotated = rotate_refresh_token(
            db,
            token,
            new_refresh_token,
            user_agent_hash=user_agent_hash,
            ip_subnet=ip_subnet,
        )
        if not rotated:
            logger.warning(
                "auth.refresh.failed",
                reason="token_already_consumed",
                user_id=user.id,
                request_id=_request_id(request),
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token already revoked or consumed",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except SessionTokenCollisionError:
        logger.warning(
            "auth.refresh.failed",
            reason="session_token_collision",
            user_id=user.id,
            request_id=_request_id(request),
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to rotate session",
        )
    except SQLAlchemyError:
        logger.exception(
            "auth.refresh.failed",
            reason="session_rotation_error",
            user_id=user.id,
            request_id=_request_id(request),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Authentication service unavailable",
        )

    csrf_token = token_urlsafe(32)
    _set_auth_cookies(response, new_refresh_token, csrf_token)
    response.headers["X-CSRF-Token"] = csrf_token

    logger.info(
        "auth.refresh.success",
        user_id=user.id,
        request_id=_request_id(request),
    )
    _audit(request, "auth.refresh", "success", user_id=user.id)

    return TokenResponse(
        access_token=new_access_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    refresh_token_cookie: str | None = Cookie(None, alias="refresh_token"),
    csrf_cookie: str | None = Cookie(None, alias="csrf_token"),
    x_csrf_token: str | None = Header(None, alias="X-CSRF-Token"),
    db: Session = Depends(get_db),
) -> None:
    """Logout user by revoking refresh token and clearing the refresh-token cookie."""
    _validate_csrf(csrf_cookie, x_csrf_token)

    if refresh_token_cookie is not None:
        try:
            revoke_refresh_token(db, refresh_token_cookie)
        except SQLAlchemyError:
            logger.exception(
                "auth.logout.failed",
                reason="session_revoke_error",
                request_id=_request_id(request),
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Authentication service unavailable",
            )

    logger.info(
        "auth.logout.success",
        had_refresh_cookie=refresh_token_cookie is not None,
        request_id=_request_id(request),
    )

    response.delete_cookie(key="refresh_token")
    response.delete_cookie(key="csrf_token")
    _audit(request, "auth.logout", "success")
    return None


@router.get("/sessions", response_model=SessionListResponse)
def get_sessions(
    refresh_token_cookie: str | None = Cookie(None, alias="refresh_token"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SessionListResponse:
    current_jti = None
    if refresh_token_cookie:
        try:
            current_jti = get_refresh_token_jti(refresh_token_cookie)
        except HTTPException:
            current_jti = None

    sessions = [
        SessionInfo(
            token_jti=s.token_jti,
            issued_at=s.issued_at,
            expires_at=s.expires_at,
            revoked_at=s.revoked_at,
            current=s.token_jti == current_jti,
        )
        for s in list_user_sessions(db, current_user.id)
    ]
    return SessionListResponse(sessions=sessions)


@router.delete("/sessions/{session_jti}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    request: Request,
    session_jti: str,
    csrf_cookie: str | None = Cookie(None, alias="csrf_token"),
    x_csrf_token: str | None = Header(None, alias="X-CSRF-Token"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    _validate_csrf(csrf_cookie, x_csrf_token)
    revoke_session_by_jti(db, current_user.id, session_jti)
    _audit(request, "auth.session.revoke", "success", user_id=current_user.id, session_id=session_jti)
    return None


@router.post("/sessions/revoke-others")
def revoke_sessions_except_current(
    request: Request,
    refresh_token_cookie: str | None = Cookie(None, alias="refresh_token"),
    csrf_cookie: str | None = Cookie(None, alias="csrf_token"),
    x_csrf_token: str | None = Header(None, alias="X-CSRF-Token"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    _validate_csrf(csrf_cookie, x_csrf_token)
    if refresh_token_cookie is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        current_jti = get_refresh_token_jti(refresh_token_cookie)
    except HTTPException as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    revoked = revoke_other_sessions(db, current_user.id, current_jti)
    _audit(request, "auth.session.revoke_others", "success", user_id=current_user.id)
    return {"revoked": revoked}


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> User:
    """Get current authenticated user information."""
    return current_user
