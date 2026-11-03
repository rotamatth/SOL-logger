"""Retired external-server Selenium entry point.

Run ``pytest tests/test_student_navigation_browser.py`` for the synthetic
Playwright replacements. The production logger.js and production search/viewer
templates now run on an isolated local server with no provider or participant
files. Coverage includes native Back logging and session identity, repeated
viewer returns, result-event deduplication and single hover listeners.

The old suite assumed a text ID field (the app now uses a select), depended on
an externally started server, and could target a live participant collection.
No tests are imported here: the replacement module is collected exactly once.
"""
