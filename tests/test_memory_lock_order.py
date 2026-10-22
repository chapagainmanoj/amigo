"""Static protection for the Memory profile/FK and optional admission lock order.

Fresh PostgreSQL interleaving and cap probes accompany independent migration review.
"""

from pathlib import Path

SQL = (Path(__file__).parents[1] / "migrations/020_durable_memory.sql").read_text()


def test_memory_parent_profile_lock_precedes_participant_advisory_lock():
    body = SQL.split("CREATE FUNCTION public.memory_command(", 1)[1]
    body = body.split("-- Deliberately preserves", 1)[0]
    assert body.index("FOR KEY SHARE") < body.index("pg_advisory_xact_lock")
    assert body.index("'amigo-memory:'") < body.index("SELECT * INTO s")
    assert body.index("SELECT * INTO s") < body.index("'amigo-memory-admission'")
    assert "IF p_operation='confirm_memory_save' AND NOT s.enabled THEN" in body


def test_scope_encoding_uses_explicit_c_collation_in_normalization_and_storage():
    assert 'array_agg(DISTINCT value COLLATE "C" ORDER BY value COLLATE "C")' in SQL
    assert 'array_agg(value COLLATE "C" ORDER BY value COLLATE "C") INTO m.scopes' in SQL
