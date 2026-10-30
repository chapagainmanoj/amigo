"""Coach check-in schedules are readable and never land inside quiet hours."""

from types import SimpleNamespace

from src.coaching import quiet_hours_conflict, schedule_text
from src.coaching_templates import TEMPLATES_BY_ID
from src.tools.coaching import draft_program
from tests.fakes import FakeChannel, FakeStore


def test_schedule_text_reads_like_a_person_wrote_it():
    assert schedule_text([1, 2, 3, 4, 5], "23:00") == "Mon to Fri at 11:00 pm"
    assert schedule_text([1, 3, 5], "07:05") == "Mon, Wed, Fri at 7:05 am"
    assert schedule_text(range(1, 8), "12:00") == "Every day at 12:00 pm"
    assert schedule_text([6, 7], "00:30") == "Sat, Sun at 12:30 am"


def test_check_in_inside_quiet_hours_is_refused():
    user = {"wake_time": "07:30", "sleep_time": "23:00"}
    assert "quiet hours" in quiet_hours_conflict(user, "23:00")
    assert "quiet hours" in quiet_hours_conflict(user, "06:00")
    assert quiet_hours_conflict(user, "07:30") is None
    assert quiet_hours_conflict(user, "22:59") is None
    assert quiet_hours_conflict({"wake_time": "06:00", "sleep_time": "23:30"}, "23:00") is None


async def test_draft_tool_refuses_a_bedtime_check_in_before_saving_anything():
    store = FakeStore()
    user = await store.create_user(5150)
    deps = SimpleNamespace(
        store=store, channel=FakeChannel(), user=user, timezone="UTC", turn_id="t",
        chat_id=5150, conversation=None,
    )
    reply = await draft_program(
        SimpleNamespace(deps=deps), "Go to bed on time", "In bed by 11pm", [1, 2, 3, 4, 5],
        "23:00",
    )
    assert "quiet hours" in reply
    assert await store.get_coaching_program(user["user_id"]) is None


def test_sleep_template_suggests_a_morning_check_in():
    note = TEMPLATES_BY_ID["sleep"].note()
    assert "the night before" in note and "8am" in note
