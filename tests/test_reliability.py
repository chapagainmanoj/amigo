"""Liveness-independent readiness checks for the Reminder Core Loop."""

from src.reliability import assess_readiness
from src.utils import utc_now
from tests.fakes import FakeStore


async def test_readiness_requires_a_scheduler_heartbeat():
    store = FakeStore()

    payload, status_code = await assess_readiness(store)

    assert status_code == 503
    assert payload["status"] == "not_ready"
    assert payload["checks"] == {
        "database": "available",
        "scheduler": "stale",
        "outbox": "available",
    }


async def test_readiness_reports_content_free_metrics_after_reconciliation():
    store = FakeStore()
    await store.record_scheduler_heartbeat(
        owner_key="beta-scheduler",
        worker_id="test-worker",
        missing_jobs=1,
        wrong_time_jobs=2,
        inverse_drift_jobs=3,
    )

    payload, status_code = await assess_readiness(store)

    assert status_code == 200
    assert payload["status"] == "ready"
    assert payload["evidence"]["reconciliation_drift"] == 6
    assert "message" not in repr(payload).lower()


async def test_readiness_fails_for_poisoned_outbox_and_database_failure():
    store = FakeStore()
    await store.record_scheduler_heartbeat(
        owner_key="beta-scheduler",
        worker_id="test-worker",
        missing_jobs=0,
        wrong_time_jobs=0,
        inverse_drift_jobs=0,
    )
    store.scheduler_outbox["failed"] = {
        "status": "failed",
        "created_at": utc_now().isoformat(),
    }

    payload, status_code = await assess_readiness(store)
    assert status_code == 503
    assert payload["checks"]["outbox"] == "failed_effects"

    class UnavailableStore:
        async def get_reminder_reliability_health(self):
            raise ConnectionError("database unavailable")

    payload, status_code = await assess_readiness(UnavailableStore())
    assert status_code == 503
    assert payload["checks"]["database"] == "unavailable"
    assert payload["failure"] == "ConnectionError"
