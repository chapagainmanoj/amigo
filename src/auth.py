"""Authentication dependencies for verifying Supabase JWTs."""

import logging
from dataclasses import dataclass

from fastapi import Header, HTTPException, status

from src.db.supabase import get_supabase

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthenticatedIdentity:
    """Server-verified Dashboard Account identity and verification state."""

    auth_id: str
    email_verified: bool
    email: str | None = None


async def get_authenticated_identity(
    authorization: str = Header(None),
) -> AuthenticatedIdentity:
    """Verify the bearer token and return the server-derived Dashboard Account identity."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header. Expected 'Bearer <token>'",
        )

    token = authorization.split(" ", 1)[1]
    supabase = await get_supabase()
    try:
        response = await supabase.auth.get_user(token)
        if not response or not response.user:
            raise ValueError("missing authenticated user")
        user = response.user
        return AuthenticatedIdentity(
            auth_id=user.id,
            email_verified=bool(
                getattr(user, "email_confirmed_at", None)
                or getattr(user, "confirmed_at", None)
            ),
            email=getattr(user, "email", None),
        )
    except Exception as error:
        logger.warning("Token verification failed: %s", str(error))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from None


async def get_authenticated_user_id(authorization: str = Header(None)) -> str:
    """Extract and verify the Supabase JWT from the Authorization header.

    Returns the user's auth UUID (auth.uid()).
    Raises HTTP 401 if invalid or missing.
    """
    return (await get_authenticated_identity(authorization)).auth_id
