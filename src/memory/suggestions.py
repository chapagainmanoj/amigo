"""Owned, content-free, single-use Mode offers for the local Stores."""

import asyncio
import copy
import uuid
from contextlib import asynccontextmanager
from datetime import timedelta
from zoneinfo import ZoneInfo

from src.agent.modes import DAILY_MODE_ID
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
            if (
                not session
                or session.get("ended_at")
                or session.get("mode_id", DAILY_MODE_ID) != DAILY_MODE_ID
            ):
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
                "opened_session_id": None,
                "control_session_id": None,
                "opening_claim_token": None,
                "opening_claimed_at": None,
                "opening_completed_at": None,
            }
            self.offers[offer["offer_id"]] = offer
            return copy.deepcopy(offer)

    async def get(self, user_id, offer_id):
        offer = self.offers.get(offer_id)
        return copy.deepcopy(offer) if offer and offer["user_id"] == user_id else None

    @asynccontextmanager
    async def _opening_locks(self):
        async with self.lock, self.store._mode_state.lock, self.store._coaching_state.lock:
            yield

    async def _opening_allowed(self, offer):
        from src.memory.memory_store import _utc_timestamp

        actor = offer["user_id"]
        if not await self.preference(actor) or await self.pending_confirmation(actor):
            return False
        if offer["grant_required"] and not await self.store._mode_state._active_grant(
            actor, offer["target_mode_id"], _utc_timestamp(utc_now())
        ):
            return False
        source = await self.owned_session(actor, offer["source_session_id"])
        selected = offer["target_mode_id"] if offer["state"] == "confirmed" else DAILY_MODE_ID
        if (
            not source
            or source.get("ended_at")
            or source.get("mode_id", DAILY_MODE_ID) != DAILY_MODE_ID
            or (source.get("active_mode_id") or DAILY_MODE_ID) != selected
        ):
            return False
        sessions = getattr(self.store, "_sessions", None)
        rows = sessions.values() if sessions is not None else self.store.sessions
        controls = [
            row
            for row in rows
            if row["user_id"] == actor
            and row.get("mode_id", DAILY_MODE_ID) == DAILY_MODE_ID
            and not row.get("ended_at")
        ]
        controls.sort(key=lambda row: (row["started_at"], row["session_id"]), reverse=True)
        if not controls or (controls[0].get("active_mode_id") or DAILY_MODE_ID) != selected:
            return False
        if (
            offer["state"] == "confirmed"
            and controls[0]["session_id"] != offer["control_session_id"]
        ):
            return False
        if offer["state"] == "confirmed":
            target = await self.owned_session(actor, offer["opened_session_id"])
            if (
                not target
                or target.get("ended_at")
                or target["mode_id"] != selected
                or target.get("active_mode_id") != selected
            ):
                return False
        return True

    async def _target_session(self, actor, target_mode):
        """Prepare the complete local transaction before publishing selector/receipt updates."""
        from src.memory.memory_store import _utc_timestamp

        user = await self.store.get_user_by_id(actor)
        timezone = ZoneInfo(user.get("timezone") or "UTC")
        now = _utc_timestamp(utc_now())
        sessions = getattr(self.store, "_sessions", None)
        rows = list(sessions.values()) if sessions is not None else self.store.sessions
        candidates = [
            row
            for row in rows
            if row["user_id"] == actor
            and row.get("mode_id", DAILY_MODE_ID) == target_mode
            and not row.get("ended_at")
        ]
        candidates.sort(key=lambda row: (row["started_at"], row["session_id"]), reverse=True)
        old = candidates[0] if candidates else None
        stale = old is not None and (
            _utc_timestamp(old["last_activity_at"])
            < now - timedelta(minutes=user.get("session_timeout_minutes") or 120)
            or _utc_timestamp(old["last_activity_at"]).astimezone(timezone).date()
            < now.astimezone(timezone).date()
        )
        if old is not None and not stale:
            old.update(active_mode_id=target_mode, last_activity_at=now.isoformat())
            return old
        target = dict(
            session_id=str(uuid.uuid4()),
            user_id=actor,
            session_type="casual",
            mode_id=target_mode,
            started_at=now.isoformat(),
            last_activity_at=now.isoformat(),
            ended_at=None,
            message_count=0,
            context_summary=None,
            active_mode_id=target_mode,
        )
        if stale:
            old["ended_at"] = now.isoformat()
        if sessions is not None:
            sessions[target["session_id"]] = target
        else:
            self.store.sessions.append(target)
        return target

    async def resolve(self, user_id, offer_id, confirm):
        if type(confirm) is not bool:
            return None
        async with self._opening_locks():
            offer = self.offers.get(offer_id)
            if not offer or offer["user_id"] != user_id or offer["state"] != "pending":
                return None
            from src.memory.memory_store import _utc_timestamp

            if _utc_timestamp(offer["expires_at"]) <= _utc_timestamp(utc_now()):
                offer["state"] = "expired"
                return None
            if not confirm:
                offer["state"] = "declined"
                return copy.deepcopy(offer)
            if not await self._opening_allowed(offer):
                offer["state"] = "declined"
                return None
            target = await self._target_session(user_id, offer["target_mode_id"])
            source = await self.owned_session(user_id, offer["source_session_id"])
            sessions = getattr(self.store, "_sessions", None)
            rows = sessions.values() if sessions is not None else self.store.sessions
            controls = [
                row
                for row in rows
                if row["user_id"] == user_id
                and row.get("mode_id", DAILY_MODE_ID) == DAILY_MODE_ID
                and not row.get("ended_at")
            ]
            controls.sort(key=lambda row: (row["started_at"], row["session_id"]), reverse=True)
            control = controls[0]
            source["active_mode_id"] = control["active_mode_id"] = offer["target_mode_id"]
            offer["control_session_id"] = control["session_id"]
            offer.update(
                state="confirmed",
                opened_session_id=target["session_id"],
                opening_claim_token=str(uuid.uuid4()),
                opening_claimed_at=utc_now().isoformat(),
            )
            return copy.deepcopy(offer)

    async def claim_opening(self, user_id, offer_id):
        from src.memory.memory_store import _utc_timestamp

        async with self._opening_locks():
            offer = self.offers.get(offer_id)
            if (
                not offer
                or offer["user_id"] != user_id
                or offer["state"] != "confirmed"
                or offer["opening_completed_at"] is not None
                or not await self._opening_allowed(offer)
            ):
                return None
            if offer["opening_claimed_at"] is not None and _utc_timestamp(
                offer["opening_claimed_at"]
            ) > _utc_timestamp(utc_now()) - timedelta(minutes=5):
                return {"status": "busy"}
            offer.update(
                opening_claim_token=str(uuid.uuid4()), opening_claimed_at=utc_now().isoformat()
            )
            return {"status": "claimed", "offer": copy.deepcopy(offer)}

    async def _owns_opening(self, offer, user_id, token):
        from src.memory.memory_store import _utc_timestamp

        return bool(
            offer
            and offer["user_id"] == user_id
            and offer["state"] == "confirmed"
            and offer["opening_completed_at"] is None
            and token is not None
            and offer["opening_claim_token"] == token
            and offer["opening_claimed_at"] is not None
            and _utc_timestamp(offer["opening_claimed_at"])
            > _utc_timestamp(utc_now()) - timedelta(minutes=5)
        )

    async def release_opening(self, user_id, offer_id, token):
        async with self.lock:
            offer = self.offers.get(offer_id)
            if not await self._owns_opening(offer, user_id, token):
                return False
            offer.update(opening_claim_token=None, opening_claimed_at=None)
            return True

    async def complete_opening(self, user_id, offer_id, token):
        async with self._opening_locks():
            offer = self.offers.get(offer_id)
            if not await self._owns_opening(
                offer, user_id, token
            ) or not await self._opening_allowed(offer):
                return False
            offer["opening_completed_at"] = utc_now().isoformat()
            return True

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
