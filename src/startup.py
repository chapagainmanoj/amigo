"""Fail-closed application startup ordering."""

from src.schema import EXPECTED_SCHEMA_VERSION


async def initialize_runtime(store, scheduler, outbox) -> None:
    """Verify the exact schema before starting scheduler-owned side effects."""
    await store.connect()
    await store.verify_schema_version(EXPECTED_SCHEMA_VERSION)
    scheduler.start()
    scheduler.start_outbox_worker(outbox.drain_once)
    scheduler.start_reconciliation(scheduler.reconcile)
    await outbox.drain_once()
    await scheduler.reload_pending()
