"""Owned, content-free, single-use Mode offers for the local Stores."""

import asyncio
import copy
import uuid
from datetime import timedelta

from src.utils import utc_now


class LocalSuggestionState:
    def __init__(self, store):
        self.store = store
        self.lock = asyncio.Lock()
        self.preferences = {}
        self.offers = {}

    async def preference(self, user_id):
        return self.preferences.get(user_id, False)

    async def set_preference(self, user_id, enabled):
        if not isinstance(enabled, bool):
            raise ValueError("Suggestion preference must be Boolean")
        async with self.lock:
            if not await self.store.get_user_by_id(user_id):
                raise ValueError("Suggestion owner unavailable")
            self.preferences[user_id] = enabled
            if not enabled:
                for offer in self.offers.values():
                    if offer["user_id"] == user_id and offer["state"] == "pending":
                        offer["state"] = "declined"
            return enabled

    async def create(self, user_id, session_id, target_mode_id, *, grant_required=True):
        if not isinstance(grant_required, bool):
            raise ValueError("Grant requirement must be Boolean")
        if target_mode_id not in {"coach", "reflect", "recommender"}:
            raise ValueError("Unsupported suggestion target")
        async with self.lock:
            session = await self.owned_session(user_id, session_id)
            if not session or session.get("ended_at") or session.get("mode_id", "daily") != "daily":
                return None
            if not await self.preference(user_id):
                return None
            if any(
                o["user_id"] == user_id and o["source_session_id"] == session_id
                for o in self.offers.values()
            ):
                return None
            if await self.pending_confirmation(user_id):
                return None
            if grant_required and not await self.store.get_active_mode_grant(
                user_id, target_mode_id
            ):
                return None
            now = utc_now()
            offer = {
                "offer_id": str(uuid.uuid4()),
                "user_id": user_id,
                "source_session_id": session_id,
                "target_mode_id": target_mode_id,
                "grant_required": grant_required,
                "state": "pending",
                "created_at": now.isoformat(),
                "expires_at": (now + timedelta(minutes=10)).isoformat(),
            }
            self.offers[offer["offer_id"]] = offer
            return copy.deepcopy(offer)

    async def get(self, user_id, offer_id):
        offer = self.offers.get(offer_id)
        return copy.deepcopy(offer) if offer and offer["user_id"] == user_id else None

    async def resolve(self, user_id, offer_id, confirm):
        if not isinstance(confirm, bool):
            return None
        async with self.lock:
            offer = self.offers.get(offer_id)
            if not offer or offer["user_id"] != user_id or offer["state"] != "pending":
                return None
            from src.memory.memory_store import _utc_timestamp

            if _utc_timestamp(offer["expires_at"]) <= _utc_timestamp(utc_now()):
                offer["state"] = "expired"
                return None
            session = await self.owned_session(user_id, offer["source_session_id"])
            if not session or session.get("ended_at") or not await self.preference(user_id):
                offer["state"] = "declined"
                return None
            if (
                confirm
                and offer["grant_required"]
                and not await self.store.get_active_mode_grant(user_id, offer["target_mode_id"])
            ):
                offer["state"] = "declined"
                return None
            offer["state"] = "confirmed" if confirm else "declined"
            return copy.deepcopy(offer)

    async def pending_confirmation(self, user_id):
        from src.memory.memory_store import _utc_timestamp

        pending_coach = any(
            row["user_id"] == user_id
            and row["used_at"] is None
            and _utc_timestamp(row["expires_at"]) > _utc_timestamp(utc_now())
            for row in self.store._coaching_state.approvals.values()
        )
        return pending_coach or any(
            row["user_id"] == user_id
            and row["resolved_at"] is None
            and _utc_timestamp(row["expires_at"]) > _utc_timestamp(utc_now())
            for row in self.store._mode_state.handoffs.values()
        )

    async def owned_session(self, user_id, session_id):
        sessions = getattr(self.store, "_sessions", None)
        if sessions is None:
            sessions = {row["session_id"]: row for row in self.store.sessions}
        row = sessions.get(session_id)
        return row if row and row["user_id"] == user_id else None
