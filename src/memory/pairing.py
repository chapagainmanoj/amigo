"""Pairing-token policy shared by Store implementations and API adapters."""

from datetime import timedelta

PAIRING_TOKEN_HEX_LENGTH = 32
PAIRING_TOKEN_LIMIT = 5
PAIRING_TOKEN_TTL = timedelta(minutes=15)
PAIRING_TOKEN_WINDOW = timedelta(minutes=15)


class PairingTokenRateLimitError(RuntimeError):
    """Raised when a Dashboard Account exceeds the Pairing-token issuance limit."""

