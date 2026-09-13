"""Row-lock order across the migration chain, checked statically.

The runtime probe in `scripts/check_activation_lock_order.py` needs a database, a forced
interleave, and luck. This does not: it reads the migration text, so a re-inversion fails
immediately and deterministically, on every machine, with no timing involved.

Migration 013's amendment exists because `create_activation_test_command` took its row locks
in the opposite order to `get_activation_state` and deadlocked the dashboard against the
participant. Nothing structural prevented that from coming back.
"""

import re
from pathlib import Path

import pytest

MIGRATIONS = sorted((Path(__file__).parents[1] / "migrations").glob("[0-9][0-9][0-9]_*.sql"))
# The required order. A function may take any prefix of this, but never a later table before
# an earlier one.
LOCK_ORDER = ("activation_journeys", "user_profiles")


def _functions() -> dict[str, str]:
    """Every function body in the chain, keyed by name so a later definition wins.

    `CREATE OR REPLACE` in a later migration is what the built database actually has, so an
    earlier definition it supersedes must not be checked — and must not be able to mask the
    live one either.
    """
    bodies: dict[str, str] = {}
    for path in MIGRATIONS:
        text = path.read_text()
        for match in re.finditer(
            r"CREATE (?:OR REPLACE )?FUNCTION\s+public\.(\w+)\s*\(", text
        ):
            start = match.end()
            end = text.find("\n$$;", start)
            bodies[match.group(1)] = text[start : end if end != -1 else len(text)]
    return bodies


# A row lock is taken by `... FROM|JOIN public.X ... FOR UPDATE`, and also by a bare
# `UPDATE public.X`, which locks every row it matches.
_LOCK_SITE = re.compile(
    r"(?P<update>UPDATE\s+public\.(?P<updated>\w+))|(?P<for_update>FOR\s+UPDATE)",
    re.IGNORECASE,
)
_SOURCE = re.compile(r"(?:FROM|JOIN)\s+public\.(\w+)", re.IGNORECASE)
# `FOR UPDATE OF a, b` locks several relations in one statement, and the order is the plan's,
# not the text's. Nothing in the chain uses it; the checker refuses it rather than guessing.
_MULTI_TARGET = re.compile(r"FOR\s+UPDATE\s+OF\s+\w+\s*,", re.IGNORECASE)


def _locked_tables_in_order(body: str) -> list[str]:
    """Tables this function row-locks, in acquisition order.

    Anchors each `FOR UPDATE` to the nearest *preceding* table reference rather than scanning
    forward from a `FROM`, so an unlocked read followed by a lock on a different table is not
    misattributed, and distance between the two cannot hide an inversion.
    """
    locked: list[str] = []
    for match in _LOCK_SITE.finditer(body):
        if match.group("update"):
            table = match.group("updated")
            # An UPDATE only acquires a lock the function does not already hold; writing back
            # to a row it locked earlier is not a second acquisition.
            if table in locked:
                continue
        else:
            sources = _SOURCE.findall(body[: match.start()])
            if not sources:
                continue
            table = sources[-1]
        if table in LOCK_ORDER:
            locked.append(table)
    return locked


@pytest.mark.parametrize("name", sorted(_functions()))
def test_every_function_takes_activation_row_locks_in_one_order(name):
    locked = _locked_tables_in_order(_functions()[name])
    ranks = [LOCK_ORDER.index(table) for table in locked]

    assert ranks == sorted(ranks), (
        f"{name} locks {locked}, which inverts the chain-wide order {list(LOCK_ORDER)}. "
        "Two functions locking these tables in opposite orders deadlock."
    )


def test_the_checker_would_catch_an_inversion():
    """Without this, the parametrized test above could be matching nothing at all."""
    inverted = """
      SELECT profile.* INTO profile_row
      FROM public.user_profiles AS profile WHERE profile.user_id = p_user_id FOR UPDATE;
      SELECT journey.* INTO journey_row
      FROM public.activation_journeys AS journey WHERE journey.auth_id = x FOR UPDATE;
    """

    locked = _locked_tables_in_order(inverted)

    assert locked == ["user_profiles", "activation_journeys"]
    ranks = [LOCK_ORDER.index(table) for table in locked]
    assert ranks != sorted(ranks)


def test_the_activation_functions_are_actually_covered():
    """Guard against the regex silently matching nothing after a migration is reformatted."""
    bodies = _functions()
    covered = {name for name, body in bodies.items() if _locked_tables_in_order(body)}

    assert "create_activation_test_command" in covered
    assert "get_activation_state" in covered
    assert "update_activation_profile" in covered


@pytest.mark.parametrize(
    "shape,body",
    [
        (
            "distance between the read and the lock",
            """
      SELECT profile.* INTO profile_row FROM public.user_profiles AS profile
      WHERE profile.user_id = p_user_id FOR UPDATE;
      -- """ + ("filler comment line\n      " * 40) + """
      SELECT journey.* INTO journey_row FROM public.activation_journeys AS journey
      WHERE journey.auth_id = x FOR UPDATE;
            """,
        ),
        (
            "a bare UPDATE taking the first lock",
            """
      UPDATE public.user_profiles SET timezone = p_timezone WHERE user_id = p_user_id;
      SELECT journey.* INTO journey_row FROM public.activation_journeys AS journey
      WHERE journey.auth_id = x FOR UPDATE;
            """,
        ),
    ],
)
def test_inversions_are_caught_whatever_shape_they_take(shape, body):
    """Each of these escaped an earlier forward-scanning matcher."""
    locked = _locked_tables_in_order(body)
    ranks = [LOCK_ORDER.index(table) for table in locked]

    assert locked[:2] == ["user_profiles", "activation_journeys"], f"{shape}: {locked}"
    assert ranks != sorted(ranks), f"{shape} was not caught"


def test_an_unlocked_read_is_not_mistaken_for_a_lock():
    """An unlocked read followed by a lock on another table must not be misattributed."""
    body = """
      SELECT profile.* INTO profile_row FROM public.user_profiles AS profile
      WHERE profile.user_id = p_user_id;

      SELECT journey.* INTO journey_row FROM public.activation_journeys AS journey
      WHERE journey.auth_id = x FOR UPDATE;
    """

    assert _locked_tables_in_order(body) == ["activation_journeys"]


def test_a_superseded_definition_does_not_mask_or_flag_the_live_one():
    """CREATE OR REPLACE means the last definition in the chain is what the database has."""
    bodies = _functions()

    assert "issue_pairing_token" in bodies
    # 013 re-creates it; the 013 text is what must be checked.
    assert "activation_not_acknowledged" in bodies["issue_pairing_token"]


def test_a_multi_target_for_update_is_refused_rather_than_guessed():
    """`FOR UPDATE OF a, b` locks in plan order, which the text cannot tell us."""
    body = """
      SELECT profile.*, journey.* FROM public.user_profiles AS profile
      JOIN public.activation_journeys AS journey
        ON journey.auth_id = profile.supabase_auth_id
      FOR UPDATE OF profile, journey;
    """

    assert _MULTI_TARGET.search(body)


@pytest.mark.parametrize("name", sorted(_functions()))
def test_no_function_locks_several_relations_in_one_statement(name):
    body = _functions()[name]

    assert not _MULTI_TARGET.search(body), (
        f"{name} uses FOR UPDATE OF with several targets; the lock order is then a plan "
        "detail this checker cannot read. Split it into one locked SELECT per table."
    )


def test_a_second_lock_on_an_already_locked_table_is_still_an_acquisition():
    """A conditional re-lock of another row is a real acquisition, not a write-back.

    This is the exact shape of the defect that shipped: a second `activation_journeys`
    FOR UPDATE taken while already holding `user_profiles`.
    """
    body = """
      SELECT journey.* INTO journey_row FROM public.activation_journeys AS journey
      WHERE journey.auth_id = x FOR UPDATE;

      SELECT profile.* INTO profile_row FROM public.user_profiles AS profile
      WHERE profile.user_id = p_user_id FOR UPDATE;

      IF journey_row.auth_id IS NOT NULL THEN
        SELECT journey.* INTO journey_row FROM public.activation_journeys AS journey
        WHERE journey.auth_id = profile_row.supabase_auth_id FOR UPDATE;
      END IF;
    """

    locked = _locked_tables_in_order(body)
    ranks = [LOCK_ORDER.index(table) for table in locked]

    assert locked == ["activation_journeys", "user_profiles", "activation_journeys"]
    assert ranks != sorted(ranks), "the conditional re-lock must be flagged"


def test_a_write_back_to_a_held_row_is_not_an_acquisition():
    """Otherwise every function that updates what it locked would look like an inversion."""
    body = """
      SELECT journey.* INTO journey_row FROM public.activation_journeys AS journey
      WHERE journey.auth_id = x FOR UPDATE;

      SELECT profile.* INTO profile_row FROM public.user_profiles AS profile
      WHERE profile.user_id = p_user_id FOR UPDATE;

      UPDATE public.activation_journeys SET updated_at = now() WHERE auth_id = x;
    """

    assert _locked_tables_in_order(body) == ["activation_journeys", "user_profiles"]
