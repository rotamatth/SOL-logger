"""Shared school-year choices for preparation and session administration."""
from .participants import valid_school_year


def school_year_choices(settings, *selected):
    """Known years include old enrollment and removed sessions after promotion."""
    values = (set(settings.get("enrollments", {}))
              | {item.get("school_year") for item in settings.get("sessions", [])}
              | {item.get("school_year") for item in settings.get("historical_grades", [])}
              | {settings.get("current_school_year"), *selected})
    return sorted((value for value in values if valid_school_year(value)), reverse=True)


def school_year_bounds(year):
    """Native date-input limits mirror the authoritative September–August rule."""
    if not valid_school_year(year):
        return None
    return {"min": year[:4] + "-09-01", "max": year[5:] + "-08-31"}
