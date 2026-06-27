"""Authentication dependencies for verifying Supabase JWTs."""

import logging

from fastapi import Header, HTTPException, status

from src.db.supabase import get_supabase

logger = logging.getLogger(__name__)


async def get_authenticated_user_id(authorization: str = Header(None)) -> str:
    """Extract and verify the Supabase JWT from the Authorization header.

    Returns the user's auth UUID (auth.uid()).
    Raises HTTP 401 if invalid or missing.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header. Expected 'Bearer <token>'",
        )

    token = authorization.split(" ")[1]
    supabase = get_supabase()

    try:
        # Call Supabase Auth API to get the user corresponding to this JWT.
        # This performs validation against Supabase Auth.
        response = supabase.auth.get_user(token)
        if not response or not response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        return response.user.id
    except Exception as e:
        logger.warning("Token verification failed: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from None

