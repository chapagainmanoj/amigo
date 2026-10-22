"""Coaching Tools: one owned Program, explicit intent, and no Task/Reminder capability."""

from uuid import UUID

from pydantic_ai import FunctionToolset, RunContext

from src.coaching import CoachingCommands, CoachingController, command_hash
from src.commands.base import CommandContext
from src.tools.context import ToolContext

COACHING: FunctionToolset[ToolContext] = FunctionToolset(max_retries=0)


def _context(deps, action, values):
    return CommandContext(
        deps.user["user_id"],
        "telegram",
        f"coach:{deps.turn_id}:{action}:{command_hash(action, values)[:24]}",
    )


@COACHING.tool
async def draft_program(
    ctx: RunContext[ToolContext],
    goal: str,
    success_measure: str,
    check_in_days: list[int],
    check_in_time: str,
) -> str:
    """Draft the participant's chosen goal and their own success measure; never starts coaching.

    Ask for all fields first. check_in_days uses Monday=1 through Sunday=7; check_in_time
    is local HH:MM. Do not invent a goal, measure, or cadence from emotional conversation.
    """
    deps = ctx.deps
    config = dict(
        goal=goal,
        success_measure=success_measure,
        check_in_days=check_in_days,
        check_in_time=check_in_time,
        timezone=deps.timezone,
    )
    result = await CoachingCommands(deps.store).draft(_context(deps, "draft", config), **config)
    row = result["program"]
    return await CoachingController(deps.store, deps.channel).show_approval(
        deps.user["user_id"],
        row["program_id"],
        deps.chat_id,
        deps.conversation,
    )


async def _change(deps, program_id, expected_version, action, **values):
    program_id = str(program_id)
    try:
        result = await CoachingCommands(deps.store).change(
            _context(
                deps, action, {"program_id": program_id, "version": expected_version, **values}
            ),
            program_id,
            expected_version,
            action,
            **values,
        )
    except ValueError:
        return "Program unavailable or changed. Refresh its current state before trying again."
    row = result["program"]
    return f"Program {row['program_id']}: {row['state']}, version {row['version']}."


@COACHING.tool
async def record_progress(
    ctx: RunContext[ToolContext],
    program_id: UUID,
    expected_version: int,
    participant_report: str,
) -> str:
    """Record only progress explicitly reported by the participant; never infer improvement."""
    return await _change(
        ctx.deps, program_id, expected_version, "record_progress", progress_text=participant_report
    )


@COACHING.tool
async def pause_program(
    ctx: RunContext[ToolContext], program_id: UUID, expected_version: int
) -> str:
    """Pause the owned Program immediately when explicitly requested."""
    return await _change(ctx.deps, program_id, expected_version, "pause")


@COACHING.tool
async def resume_program(
    ctx: RunContext[ToolContext], program_id: UUID, expected_version: int
) -> str:
    """Resume an explicitly requested paused Program within its existing approved term."""
    return await _change(ctx.deps, program_id, expected_version, "resume")


@COACHING.tool
async def stop_program(
    ctx: RunContext[ToolContext], program_id: UUID, expected_version: int
) -> str:
    """Stop the owned Program immediately when requested; stopped Programs cannot resume."""
    return await _change(ctx.deps, program_id, expected_version, "stop")


@COACHING.tool
async def extend_program(
    ctx: RunContext[ToolContext],
    program_id: UUID,
    expected_version: int,
    days: int,
) -> str:
    """Extend only after explicit participant intent, by 1–14 days; never automatically."""
    return await _change(ctx.deps, program_id, expected_version, "extend", extension_days=days)


@COACHING.tool
async def record_weekly_choice(
    ctx: RunContext[ToolContext],
    program_id: UUID,
    expected_version: int,
    choice: str,
) -> str:
    """Record the participant's continue, adjust, pause, or stop choice. Continue never extends."""
    return await _change(
        ctx.deps, program_id, expected_version, "record_weekly_choice", weekly_choice=choice
    )


@COACHING.tool
async def revise_program(
    ctx: RunContext[ToolContext],
    program_id: UUID,
    expected_version: int,
    goal: str,
    success_measure: str,
    check_in_days: list[int],
    check_in_time: str,
) -> str:
    """Revise an explicitly requested draft; approval of the exact revised summary is required."""
    deps = ctx.deps
    program_id = str(program_id)
    config = dict(
        goal=goal,
        success_measure=success_measure,
        check_in_days=check_in_days,
        check_in_time=check_in_time,
        timezone=deps.timezone,
    )
    result = await CoachingCommands(deps.store).revise(
        _context(deps, "revise", {"program_id": program_id, "version": expected_version, **config}),
        program_id,
        expected_version,
        **config,
    )
    return await CoachingController(deps.store, deps.channel).show_approval(
        deps.user["user_id"],
        result["program"]["program_id"],
        deps.chat_id,
        deps.conversation,
    )
