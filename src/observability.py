"""Content-free runtime measurements used by staging and operator evidence."""

import asyncio
import logging

logger = logging.getLogger(__name__)


async def monitor_event_loop_delay(
    stop_event: asyncio.Event,
    *,
    interval_seconds: float = 1.0,
    sample_limit: int | None = None,
) -> None:
    """Log scheduler delay without retaining participant or request data."""
    loop = asyncio.get_running_loop()
    samples = 0
    while not stop_event.is_set():
        expected_at = loop.time() + interval_seconds
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            delay_ms = max(0.0, (loop.time() - expected_at) * 1000)
            logger.info("event_loop_delay_ms=%.3f", delay_ms)
            samples += 1
            if sample_limit is not None and samples >= sample_limit:
                return


# Per-second and per-call evidence lines. Staging/production keep them for
# scripts/summarize_runtime_evidence.py; locally they bury everything else.
ROUTINE_LOGGERS = ("src.observability", "src.memory.store", "apscheduler")


def quiet_routine_logs(quiet: bool = True) -> None:
    """Raise routine evidence loggers to WARNING, or restore them to inherit the root level."""
    for name in ROUTINE_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING if quiet else logging.NOTSET)
