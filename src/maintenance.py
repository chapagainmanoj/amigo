"""Error-isolated maintenance steps; cancellation always propagates."""

import logging

logger = logging.getLogger(__name__)


async def run_isolated_steps(steps):
    for name, step in steps:
        try:
            await step()
        except Exception as error:
            logger.warning("maintenance_step=%s error_type=%s", name, type(error).__name__)
