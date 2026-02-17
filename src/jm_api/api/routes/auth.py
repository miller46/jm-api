"""Authentication routes."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.orm import Session

from jm_api.api.deps import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    hash_password,
    is_refresh_token_revoked,
    revoke_refresh_token,
    verify_password,
)
from jm_api.core.config import get_settings
from jm_api.db.session import get_db
from jm_api.models.user import User
from jm_api.schemas.auth import LoginRequest, TokenResponse, UserCreate, UserResponse

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/auth", tags=["authentication"])
logger = structlog.get_logger(__name__)


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


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

    settings = get_settings()
    logger.info(
        "auth.login.success",
        user_id=user.id,
        email=user.email,
        request_id=_request_id(request),
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        max_age=settings.jwt_refresh_token_expire_days * 24 * 60 * 60,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("3 per 15 minutes")
def signup(
    request: Request,
    user_data: UserCreate,
    db: Session = Depends(get_db),
) -> User:
    """Register a new user.

    Rate limited to 3 attempts per 15 minutes per IP address.
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
        is_admin=user_data.is_admin,
    )

    db.add(new_user)
    db.commit()
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

    if is_refresh_token_revoked(token):
        logger.warning(
            "auth.refresh.failed",
            reason="refresh_token_revoked",
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
    revoke_refresh_token(token)

    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=settings.environment == "production",
        samesite="lax",
        max_age=settings.jwt_refresh_token_expire_days * 24 * 60 * 60,
    )

    logger.info(
        "auth.refresh.success",
        user_id=user.id,
        request_id=_request_id(request),
    )

    return TokenResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    refresh_token_cookie: str | None = Cookie(None, alias="refresh_token"),
) -> None:
    """Logout user by revoking refresh token and clearing the refresh-token cookie."""
    if refresh_token_cookie is not None:
        revoke_refresh_token(refresh_token_cookie)

    logger.info(
        "auth.logout.success",
        had_refresh_cookie=refresh_token_cookie is not None,
        request_id=_request_id(request),
    )

    response.delete_cookie(key="refresh_token")
    return None


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> User:
    """Get current authenticated user information."""
    return current_user
