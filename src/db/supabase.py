"""Asynchronous Supabase client singleton."""

import asyncio

from supabase import AsyncClient, acreate_client

from src.config import settings

_client: AsyncClient | None = None
_client_lock = asyncio.Lock()


async def get_supabase() -> AsyncClient:
    """Return one reusable non-blocking Supabase client instance."""
    global _client
    if _client is not None:
        return _client
    async with _client_lock:
        if _client is None:
            _client = await acreate_client(
                settings.supabase_url,
                settings.supabase_service_key,
            )
    return _client
