"""Content-free runtime readiness derived from durable reliability evidence."""

import logging

logger = logging.getLogger(__name__)


async def assess_readiness(store) -> tuple[dict, int]:
    """Return readiness evidence and its HTTP status without affecting liveness."""
    try:
        health = await store.get_reminder_reliability_health()
    except Exception as error:
        logger.exception("Readiness database check failed")
        return {
            "status": "not_ready",
            "checks": {
                "database": "unavailable",
                "scheduler": "unknown",
                "outbox": "unknown",
            },
            "failure": type(error).__name__,
        }, 503

    scheduler_ready = bool(health.get("scheduler_ready"))
    outbox_ready = int(health.get("outbox_failed") or 0) == 0
    ready = scheduler_ready and outbox_ready
    return {
        "status": "ready" if ready else "not_ready",
        "checks": {
            "database": "available",
            "scheduler": "available" if scheduler_ready else "stale",
            "outbox": "available" if outbox_ready else "failed_effects",
        },
        "evidence": health,
    }, 200 if ready else 503
