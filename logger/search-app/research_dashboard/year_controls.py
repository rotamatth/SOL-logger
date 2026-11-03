"""Shared school-year choices for preparation and session administration."""
from .participants import valid_school_year


def school_year_choices(settings, *selected):
    """Known years include old enrollment and removed sessions after promotion."""
    values = (set(settings.get("enrollments", {}))
              | {item.get("school_year") for item in settings.get("sessions", [])}
              | {item.get("school_year") for item in settings.get("historical_grades", [])}
              | {settings.get("current_school_year"), *selected})
    return sorted((value for value in values if valid_school_year(value)), reverse=True)

