"""Explicit school-year configuration for synthetic test sessions."""
from datetime import date


def school_year(day):
    day = date.fromisoformat(day) if isinstance(day, str) else day
    start = day.year if day.month >= 9 else day.year - 1
    return f"{start}/{start+1}"


def enroll_initial_roster(settings, year='2026/2027'):
    settings['current_school_year'] = year
    for item in settings['sessions']:
        item['school_year'] = school_year(item['date']) if item.get('date') else year
    return settings
