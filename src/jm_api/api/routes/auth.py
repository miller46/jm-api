"""Authentication routes."""

from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
import structlog
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.orm import Session

from jm_api.api.deps import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    is_refresh_token_revoked,
    revoke_refresh_token,
    verify_password,
)
from jm_api.core.config import get_settings
from jm_api.db.session import get_db
from jm_api.models.user import User
from jm_api.schemas.auth import LoginRequest, TokenResponse, UserResponse

# Create limiter for rate limiting
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/auth", tags=["authentication"])
logger = structlog.get_logger(__name__)


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
    # Find user by email
    user = db.execute(
        select(User).where(User.email == login_data.email)
    ).scalar_one_or_none()

    # Verify user exists and password is correct
    if user is None or not verify_password(login_data.password, user.password_hash):
        logger.warning(
            "auth.login.failed",
            email=login_data.email,
            reason="invalid_credentials",
            request_id=getattr(request.state, "request_id", None),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        logger.warning(
            "auth.login.failed",
            email=login_data.email,
            reason="user_inactive",
            request_id=getattr(request.state, "request_id", None),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is deactivated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create tokens
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)

    # Set refresh token in httpOnly cookie
    settings = get_settings()
    logger.info(
        "auth.login.success",
        user_id=user.id,
        email=user.email,
        request_id=getattr(request.state, "request_id", None),
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
            request_id=getattr(request.state, "request_id", None),
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
            request_id=getattr(request.state, "request_id", None),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Decode and validate refresh token
    token_payload = decode_token(token)

    if token_payload.type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user
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

    # Rotate refresh token: revoke old one and set a new one in cookie
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
        request_id=getattr(request.state, "request_id", None),
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
        "auth.logout",
        had_refresh_cookie=refresh_token_cookie is not None,
        request_id=getattr(request.state, "request_id", None),
    )

    response.delete_cookie(key="refresh_token")
    return None


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> User:
    """Get current authenticated user information."""
    return current_user
