"""Supabase dashboard sessions last until their last activity, not until a lazy close."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from src.memory.store import MemoryStore


async def test_lazily_closed_session_duration_uses_last_activity():
    snapshot = {
        "sessions": [
            {
                "started_at": "2026-10-22T09:35:35+00:00",
                "last_activity_at": "2026-10-22T09:50:35+00:00",
                # Closed at the next morning's message, 17 hours later.
                "ended_at": "2026-10-23T02:51:24+00:00",
                "duration_minutes": 1036,
            },
            {"started_at": "2026-10-23T02:51:24+00:00", "last_activity_at": None},
        ]
    }
    api = MemoryStore()
    query = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(data=snapshot)))
    api.db = SimpleNamespace(rpc=Mock(return_value=query))

    result = await api.get_dashboard_snapshot("owner")

    assert [row["duration_minutes"] for row in result["sessions"]] == [15, 0]
