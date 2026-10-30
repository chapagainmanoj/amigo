"""Ready-made Coach goals a participant can pick on the dashboard instead of typing one."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CoachTemplate:
    id: str
    title: str
    goal: str
    success_measure: str
    check_in_days: str
    example_reply: str = "Mon, Wed, Fri at 7am"

    def note(self) -> str:
        """Sent in Coach after the participant picks this template; Coach drafts from the reply."""
        return (
            f"You picked “{self.title}”.\n"
            f"Goal: {self.goal}\n"
            f"Success measure: {self.success_measure}\n"
            f"Suggested check-in days: {self.check_in_days}\n\n"
            "Reply with your check-in days and time, or change anything above. "
            f"e.g. “{self.example_reply}”"
        )


COACH_TEMPLATES = (
    CoachTemplate(
        "workout", "Work out regularly", "Work out 3 times a week",
        "A 30-minute workout on each check-in day", "Mon, Wed, Fri",
    ),
    CoachTemplate(
        "walk", "Walk every day", "Walk more", "A 20-minute walk on each check-in day",
        "Every day",
    ),
    CoachTemplate(
        # Checked the next morning: a bedtime check-in would land in quiet hours.
        "sleep", "Sleep on time", "Go to bed on time",
        "In bed by 11pm the night before each check-in", "Mon to Fri",
        example_reply="Mon to Fri at 8am",
    ),
    CoachTemplate(
        "read", "Read daily", "Read more", "Read 10 pages on each check-in day", "Weekdays",
    ),
    CoachTemplate(
        "alcohol", "Drink less", "Drink less alcohol", "No alcohol on each check-in day",
        "Mon, Tue, Wed, Thu",
    ),
    CoachTemplate(
        "mindful", "Daily calm minutes", "Take quiet time for myself",
        "10 quiet minutes (breathing or sitting still) on each check-in day", "Every day",
    ),
    CoachTemplate(
        "screen", "Less screen time", "Spend less time on my phone",
        "No phone for the first 30 minutes after waking on each check-in day", "Weekdays",
    ),
    CoachTemplate(
        "learn", "Learn a skill", "Practise a new skill",
        "15 minutes of practice on each check-in day", "Mon, Wed, Fri, Sat",
    ),
)

TEMPLATES_BY_ID = {template.id: template for template in COACH_TEMPLATES}
