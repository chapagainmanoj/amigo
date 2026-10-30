"""Local mirror of migration 022: channel identities, primary channel and channel update claims.

InMemoryStore and FakeStore share this so both follow the Supabase RPC decisions exactly:
`complete_pairing_v2`, `set_primary_channel`, `claim_channel_update`, `finish_channel_update` and
the `telegram_chat_id` mirror trigger.
"""

import copy
import re
from collections.abc import Callable, Iterable
from datetime import datetime
from zoneinfo import ZoneInfo

from src.utils import utc_now

CHANNEL_PATTERN = re.compile(r"[a-z][a-z0-9_]{1,31}")
TELEGRAM_ID_PATTERN = re.compile(r"-?[1-9][0-9]{0,17}")
TELEGRAM_UPDATE_ID_PATTERN = re.compile(r"0|[1-9][0-9]{0,17}")
TELEGRAM_MESSAGE_ID_PATTERN = re.compile(r"[1-9][0-9]{0,17}")
_UPDATE_KINDS = {"message", "callback_query"}


class ChannelNotLinkedError(ValueError):
    """The participant has no identity on the requested primary channel."""


def validate_identity(channel: str, external_id: str) -> None:
    """Reject malformed identities the same way `complete_pairing_v2` does."""
    if (
        not isinstance(channel, str) or not CHANNEL_PATTERN.fullmatch(channel)
        or not isinstance(external_id, str) or not 1 <= len(external_id) <= 200
        or external_id != external_id.strip()
        or (channel == "telegram" and not TELEGRAM_ID_PATTERN.fullmatch(external_id))
    ):
        raise ValueError("invalid_channel_identity")


def _token_usable(row: dict | None, now: datetime) -> bool:
    if not row or row["consumed"] or row.get("invalidated_at"):
        return False
    expires_at = datetime.fromisoformat(row["expires_at"])
    if expires_at.tzinfo is not None:
        expires_at = expires_at.astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
    return expires_at > now


def _bounded(value: object, limit: int = 200) -> bool:
    return isinstance(value, str) and 1 <= len(value) <= limit


def finish_claim(row: dict | None, *, status: str, failure_code: str | None, label: str) -> dict:
    """Shared 009/022 finish rules: validate, finish once, replay the same outcome idempotently."""
    if status not in {"completed", "failed"}:
        raise ValueError(f"invalid_{label}_update_status")
    if (status == "completed" and failure_code is not None) or (
        status == "failed" and not _bounded(failure_code, 100)
    ):
        raise ValueError(f"invalid_{label}_failure_code")
    if row is None:
        raise ValueError(f"{label}_update_not_found")
    if row["status"] == "processing":
        row.update(status=status, failure_code=failure_code, finished_at=utc_now().isoformat())
    elif (row["status"], row["failure_code"]) != (status, failure_code):
        raise ValueError(f"{label}_update_already_finished")
    return copy.deepcopy(row)


def claim_telegram(
    claims: dict[int, dict], update_id: int, chat_id: int, update_kind: str
) -> dict:
    """009 `claim_telegram_update`: first claim wins; a replay must carry the same identity."""
    if update_kind not in _UPDATE_KINDS:
        raise ValueError("invalid_telegram_update_kind")
    existing = claims.get(update_id)
    if existing:
        if (existing["telegram_chat_id"], existing["update_kind"]) != (chat_id, update_kind):
            raise ValueError("telegram_update_identity_conflict")
        return {"claimed": False, **copy.deepcopy(existing)}
    row = {
        "update_id": update_id,
        "telegram_chat_id": chat_id,
        "update_kind": update_kind,
        "status": "processing",
        "failure_code": None,
        "claimed_at": utc_now().isoformat(),
        "finished_at": None,
    }
    claims[update_id] = row
    return {"claimed": True, **copy.deepcopy(row)}


def telegram_claim_ids(update_id: str, external_id: str | None = None) -> tuple[int, int | None]:
    """`claim_channel_update`'s Telegram ids: canonical digits only, never coerced."""
    if not isinstance(update_id, str) or not TELEGRAM_UPDATE_ID_PATTERN.fullmatch(update_id) or (
        external_id is not None
        and (not isinstance(external_id, str) or not TELEGRAM_ID_PATTERN.fullmatch(external_id))
    ):
        raise ValueError("invalid_channel_update")
    return int(update_id), int(external_id) if external_id is not None else None


def delivery_columns(
    *, accepted: bool, channel: str, telegram_message_id: int | None,
    channel_message_ref: str | None,
) -> dict | None:
    """`finish_reminder_delivery_v2` validation, before any write; columns to set on accept."""
    if not isinstance(channel, str) or not CHANNEL_PATTERN.fullmatch(channel):
        raise ValueError("invalid_delivery_channel")
    if not accepted:
        return None
    ref = delivery_message_ref(channel, telegram_message_id, channel_message_ref)
    if not _bounded(ref) or (
        channel == "telegram" and not TELEGRAM_MESSAGE_ID_PATTERN.fullmatch(ref)
    ):
        raise ValueError("accepted_delivery_requires_message_id")
    return {
        "telegram_message_id": int(ref) if channel == "telegram" else None,
        "delivery_channel": channel,
        "channel_message_ref": ref,
    }


class LocalIdentityState:
    """Identity rows keyed by (user_id, channel), unique by (channel, external_id)."""

    def __init__(self) -> None:
        self._identities: dict[tuple[str, str], dict] = {}
        self._update_claims: dict[tuple[str, str], dict] = {}

    def owner(self, channel: str, external_id: str) -> str | None:
        return next(
            (
                user_id for (user_id, row_channel), row in self._identities.items()
                if row_channel == channel and row["external_id"] == external_id
            ),
            None,
        )

    def for_user(self, user_id: str) -> dict[str, str]:
        return {
            channel: row["external_id"]
            for (owner, channel), row in sorted(self._identities.items())
            if owner == user_id
        }

    def link(self, user_id: str, channel: str, external_id: str) -> None:
        current = self.owner(channel, external_id)
        if current not in (None, user_id):
            raise ValueError("Channel identity belongs to another participant")
        self._identities[(user_id, channel)] = {
            "external_id": external_id, "linked_at": utc_now().isoformat(),
        }

    def mirror_telegram(self, user: dict) -> None:
        """The 022 trigger: `telegram_chat_id` writes keep the Telegram identity in step."""
        chat_id = user.get("telegram_chat_id")
        current = self._identities.get((user["user_id"], "telegram"))
        if chat_id is None:
            self._identities.pop((user["user_id"], "telegram"), None)
        elif current is None or current["external_id"] != str(chat_id):
            self.link(user["user_id"], "telegram", str(chat_id))

    def require_primary_linked(self, user: dict) -> None:
        """The deferred `user_profiles_primary_channel_linked` key."""
        channel = user.get("primary_channel", "telegram")
        if (user["user_id"], channel) not in self._identities:
            raise ChannelNotLinkedError("channel_not_linked")

    def write_profile(
        self, user: dict, updates: dict, *, identity: tuple[str, str] | None = None
    ) -> dict:
        """Apply a profile write as one transaction: mirror trigger, then the deferred key."""
        saved = copy.deepcopy(self._identities)
        candidate = {**user, **updates}
        try:
            if "telegram_chat_id" in updates or "user_id" in updates:
                self.mirror_telegram(candidate)
            if identity:
                self.link(candidate["user_id"], *identity)
            self.require_primary_linked(candidate)
        except ValueError:
            self._identities = saved
            raise
        user.update(updates)
        return user

    def complete_pairing(
        self,
        *,
        users: Iterable[dict],
        tokens: dict[str, dict],
        token: str,
        channel: str,
        external_id: str,
        insert_user: Callable[..., dict],
    ) -> dict:
        """Mirror `complete_pairing` (Telegram) and `complete_pairing_v2` (other channels)."""
        validate_identity(channel, external_id)
        row = tokens.get(token)
        if not _token_usable(row, utc_now()):
            return {"status": "invalid_token"}
        auth_id = row["supabase_auth_id"]
        users = list(users)
        auth_user = next((u for u in users if u.get("supabase_auth_id") == auth_id), None)
        if channel == "telegram":
            # 015 reads telegram_chat_id itself; the identity row is only its mirror.
            owner = next(
                (u for u in users if u.get("telegram_chat_id") == int(external_id)), None
            )
            owner_id = owner["user_id"] if owner else None
        else:
            owner_id = self.owner(channel, external_id)
            owner = next((u for u in users if u["user_id"] == owner_id), None)
        if owner and auth_user and owner["user_id"] == auth_user["user_id"]:
            row["consumed"] = True
            return {"status": "already_paired"}
        if channel == "telegram":
            if (
                (owner and auth_user)
                or (owner and owner.get("supabase_auth_id") not in (None, auth_id))
                or (auth_user and auth_user.get("telegram_chat_id") not in (
                    None, int(external_id)))
            ):
                return {"status": "conflict"}
            now = utc_now().isoformat()
            if owner:
                owner.update(supabase_auth_id=auth_id, updated_at=now)
            elif auth_user:
                auth_user.update(telegram_chat_id=int(external_id), updated_at=now)
                self.mirror_telegram(auth_user)
            else:
                insert_user({"telegram_chat_id": int(external_id), "supabase_auth_id": auth_id})
        else:
            if owner_id is not None or (
                auth_user and (auth_user["user_id"], channel) in self._identities
            ):
                return {"status": "conflict"}
            if auth_user:
                auth_user["updated_at"] = utc_now().isoformat()
                self.link(auth_user["user_id"], channel, external_id)
            else:
                insert_user(
                    {"supabase_auth_id": auth_id, "primary_channel": channel},
                    identity=(channel, external_id),
                )
        row["consumed"] = True
        return {"status": "paired"}

    def claim_update(
        self, channel: str, update_id: str, external_id: str, update_kind: str
    ) -> dict:
        """`claim_channel_update` for channels other than Telegram."""
        if (
            not isinstance(channel, str) or not CHANNEL_PATTERN.fullmatch(channel)
            or channel == "telegram" or not _bounded(update_id) or not _bounded(external_id)
        ):
            raise ValueError("invalid_channel_update")
        if update_kind not in _UPDATE_KINDS:
            raise ValueError("invalid_channel_update_kind")
        existing = self._update_claims.get((channel, update_id))
        if existing:
            if (existing["external_id"], existing["update_kind"]) != (external_id, update_kind):
                raise ValueError("channel_update_identity_conflict")
            return {"claimed": False, **copy.deepcopy(existing)}
        row = {
            "channel": channel,
            "update_id": update_id,
            "external_id": external_id,
            "update_kind": update_kind,
            "status": "processing",
            "failure_code": None,
            "claimed_at": utc_now().isoformat(),
            "finished_at": None,
        }
        self._update_claims[(channel, update_id)] = row
        return {"claimed": True, **copy.deepcopy(row)}

    def finish_update(
        self, channel: str, update_id: str, *, status: str, failure_code: str | None
    ) -> dict:
        """`finish_channel_update` for channels other than Telegram; replays are idempotent."""
        if (
            not isinstance(channel, str) or not CHANNEL_PATTERN.fullmatch(channel)
            or not _bounded(update_id)
        ):
            raise ValueError("invalid_channel_update")
        return finish_claim(
            self._update_claims.get((channel, update_id)),
            status=status, failure_code=failure_code, label="channel",
        )


def delivery_message_ref(
    channel: str, telegram_message_id: int | None, channel_message_ref: str | None
) -> str | None:
    """The `channel_message_ref` that `finish_reminder_delivery_v2` records."""
    if channel_message_ref is not None:
        return channel_message_ref
    if channel == "telegram" and telegram_message_id is not None:
        return str(telegram_message_id)
    return None


def telegram_update_as_channel(row: dict) -> dict:
    """Reshape a Telegram claim to the channel-neutral keys, as `claim_channel_update` does."""
    result = {
        key: value for key, value in row.items() if key not in {"telegram_chat_id", "update_id"}
    }
    result.update(
        channel="telegram",
        update_id=str(row["update_id"]),
        external_id=str(row["telegram_chat_id"]),
    )
    return result
