"""Retired external-server Selenium BFCache simulation entry point.

Run ``pytest tests/test_student_navigation_browser.py`` for the synthetic
Playwright replacements. They simulate persisted pageshow events, verify recovery
to the last allowed URL, resynchronize stored logs, preserve authoritative server
session identity, and check listener/result-event deduplication after five
restores. No tests are imported here, so pytest collects replacements once.

The old expectation that localStorage could replace the server-issued session ID
was obsolete. Simulated pageshow does not prove actual BFCache behavior: real
PC/iPad acceptance remains required for that browser/device-specific check.
"""
