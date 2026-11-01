"""Logs stay content-free (cosmic-python BP-LOGS-AT-THE-EDGES).

Log ids, counts and error type names; never Task titles, time expressions or message text.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
LOG_METHODS = {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}
# Identifiers that hold participant-authored content.
CONTENT_NAMES = {
    "title", "task_title", "text", "time_expr", "time_expression", "content", "body",
    "message", "message_text", "user_message", "user_text", "reply", "raw", "prompt", "note",
    "summary", "output", "query",
}


def _is_logger(receiver: ast.AST) -> bool:
    """``logger``, ``_logger``, ``self.logger``, ``logging``, ``logging.getLogger(...)``..."""
    return "log" in ast.unparse(receiver).lower()


def _names(node: ast.AST) -> set[str]:
    found = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            found.add(child.id)
        elif isinstance(child, ast.Attribute):
            found.add(child.attr)
        elif isinstance(child, ast.Subscript) and isinstance(child.slice, ast.Constant):
            found.add(str(child.slice.value))
        elif (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr in {"get", "pop", "getattr"}
            and child.args
            and isinstance(child.args[0], ast.Constant)
        ):
            found.add(str(child.args[0].value))  # task.get("title")
        elif (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "getattr"
            and len(child.args) > 1
            and isinstance(child.args[1], ast.Constant)
        ):
            found.add(str(child.args[1].value))  # getattr(task, "title")
    return found


def _log_calls(tree: ast.AST):
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in LOG_METHODS
            and _is_logger(node.func.value)
        ):
            yield node


def _content_used(call: ast.Call) -> set[str]:
    """Content names in every argument, the message included, and every keyword (``extra=``).

    Function names of calls in the arguments are not values, so ``type(error).__name__`` and
    ``len(text)`` count as safe.
    """
    used = set()
    for arg in [*call.args, *(keyword.value for keyword in call.keywords)]:
        used |= _names(arg) - _callee_names(arg)
        used -= _counted_names(arg)
    return used & CONTENT_NAMES


def _callee_names(node: ast.AST) -> set[str]:
    return {
        child.func.id for child in ast.walk(node)
        if isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
    }


def _counted_names(node: ast.AST) -> set[str]:
    """Names only measured, never printed: ``len(text)``, ``type(error)``."""
    return {
        name
        for child in ast.walk(node)
        if isinstance(child, ast.Call)
        and isinstance(child.func, ast.Name)
        and child.func.id in {"len", "type", "bool"}
        for name in _names(child)
    }


def _hits(source: str, where: str) -> list[str]:
    return [
        f"{where}:{call.lineno} {sorted(_content_used(call))}"
        for call in _log_calls(ast.parse(source))
        if _content_used(call)
    ]


def test_log_calls_carry_no_participant_content():
    hits = [
        hit
        for path in sorted(SRC.rglob("*.py"))
        for hit in _hits(path.read_text(), str(path.relative_to(SRC.parent)))
    ]
    assert not hits, f"log ids or type names instead of content: {hits}"


def test_the_guard_sees_every_leak_form():
    leaks = [
        'logger.info("x %s", task["title"])',
        'logger.info("x %s", task.get("title"))',
        'logger.info(f"x {title}")',
        'logger.info("x %s" % title)',
        'logger.info("x {}".format(text))',
        'logger.info("x", extra={"v": message})',
        'logging.getLogger(__name__).warning("x %s", reply)',
        'self._logger.error("x %s", getattr(task, "title"))',
        'log.exception("x %s", user_message)',
    ]
    for leak in leaks:
        assert _hits(leak, "snippet"), leak


def test_the_guard_allows_ids_counts_and_error_types():
    safe = [
        'logger.info("Scheduled reminder %s at %s", job_id, send_time)',
        'logger.warning("failed: %s", type(error).__name__)',
        'logger.info("chars=%d", len(text))',
        'logger.info("task %s", task["task_id"])',
    ]
    for line in safe:
        assert not _hits(line, "snippet"), line
