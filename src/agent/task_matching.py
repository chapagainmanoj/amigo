"""Task-list and task-title matching helpers for agent planning."""


class TaskMatcher:
    """Owns lightweight task intent and title matching heuristics."""

    def looks_like_task_list(self, text: str) -> bool:
        """Return whether a message is likely listing today's tasks."""
        import re

        lower = text.lower()
        indicators = [
            "today" in lower,
            "need to" in lower,
            "want to" in lower,
            "going to" in lower,
            "plan" in lower,
            "i will" in lower or "i'll" in lower,
            "have to" in lower or "gotta" in lower,
            "then" in lower or "after that" in lower,
            bool(re.search(r"\bat\s+\d{1,2}(:\d{2})?\s*(am|pm|AM|PM)?", text)),
            bool(re.search(r"\bin\s+\d+\s*(min|hour|hr)", lower)),
            "," in text,
            "\n" in text,
            text.count(".") >= 2,
        ]
        return sum(indicators) >= 2

    def fuzzy_match_task(self, title_match: str, tasks: list[dict]) -> dict | None:
        """Simple title match for Phase 1a status updates."""
        needle = title_match.lower().strip()
        for task in tasks:
            haystack = task["title"].lower()
            if needle in haystack or haystack in needle:
                return task

        needle_words = set(needle.split())
        best_task = None
        best_overlap = 0
        for task in tasks:
            task_words = set(task["title"].lower().split())
            overlap = len(needle_words & task_words)
            if overlap > best_overlap:
                best_overlap = overlap
                best_task = task
        return best_task if best_overlap > 0 else None
