"""Application schema-version contract enforced before external side effects start."""

EXPECTED_SCHEMA_VERSION = 14


class SchemaVersionMismatchError(RuntimeError):
    """Raised when the connected database is not the exact application schema revision."""


def require_schema_version(actual: object, expected: int = EXPECTED_SCHEMA_VERSION) -> int:
    """Return the exact integer version or fail closed without accepting coercion."""
    if type(actual) is not int or actual != expected:
        raise SchemaVersionMismatchError(
            f"Database schema version mismatch: expected {expected}, received {actual!r}"
        )
    return actual
