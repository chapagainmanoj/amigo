"""Task-list and task-title matching helpers."""


class TaskMatcher:
    """Owns lightweight task intent and title matching heuristics."""

    def looks_like_task_list(self, text: str) -> bool:
        """Return whether a message is likely listing today's tasks."""
        indicators = [
            "today" in text.lower(),
            "need to" in text.lower(),
            "want to" in text.lower(),
            "going to" in text.lower(),
            "plan" in text.lower(),
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
