"""
Tests for back button navigation logging.

This test reproduces the BFCache-related issue where the logger fails to
capture the 'wentBack' event when users click the browser back button.

Requirements:
    - selenium
    - pytest
    - Flask app running (or use the fixture)
    - Chrome/Chromium with chromedriver

Run with: pytest tests/test_back_navigation.py -v
"""

import json
import time
import pytest
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options


@pytest.fixture(scope="module")
def chrome_options():
    """Configure Chrome options for testing."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    # Enable BFCache for testing (Chrome 96+)
    options.add_argument("--enable-features=BackForwardCache")
    return options


@pytest.fixture(scope="module")
def driver(chrome_options):
    """Create a Selenium WebDriver instance."""
    driver = webdriver.Chrome(options=chrome_options)
    driver.implicitly_wait(10)
    yield driver
    driver.quit()


@pytest.fixture(scope="module")
def app_url(base_url):
    """
    Return the URL of the running Flask app.

    For integration testing, the app should be running separately.
    Set the SEARCH_APP_URL environment variable to override the default.
    """
    return base_url


def clear_local_storage(driver):
    """Clear localStorage to reset logger state."""
    driver.execute_script("window.localStorage.clear();")


def get_session_logs(driver):
    """Retrieve logged events from localStorage."""
    logs_json = driver.execute_script(
        "return window.localStorage.getItem('sessionLogs');"
    )
    if logs_json:
        return json.loads(logs_json)
    return []


def get_browser_history(driver):
    """Retrieve browser history tracker from localStorage."""
    history_json = driver.execute_script(
        "return window.localStorage.getItem('browserHistory');"
    )
    if history_json:
        return json.loads(history_json)
    return []


class TestBackNavigationLogging:
    """Tests for back navigation event logging."""

    def test_went_back_event_logged_on_back_navigation(self, driver, app_url, test_user_id):
        """
        Test that 'wentBack' event is logged when user navigates back to SERP.

        Steps:
        1. Navigate to start page and enter user ID
        2. Submit a search query
        3. Click on a search result
        4. Press browser back button
        5. Verify 'wentBack' event is in the logs
        """
        # Clear any existing state
        driver.get(app_url + "/start")
        clear_local_storage(driver)

        # Enter user ID (use a test ID that exists in uids.txt)
        try:
            id_input = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "id-box"))
            )
            id_input.clear()
            id_input.send_keys(test_user_id)

            # Submit the form
            form = driver.find_element(By.ID, "enter-id-form")
            form.submit()
        except Exception:
            # If start page doesn't require ID, navigate directly
            driver.get(app_url)

        # Wait for home page and submit a search query
        search_box = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "search-box"))
        )
        search_box.clear()
        search_box.send_keys("test query")
        search_box.send_keys(Keys.RETURN)

        # Wait for search results
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "article.content-section"))
        )

        # Get initial log count
        initial_logs = get_session_logs(driver)
        initial_log_count = len(initial_logs)

        # Verify searchResultGenerated events were logged
        result_events = [
            log for log in initial_logs
            if log.get("type") == "searchResultGenerated"
        ]
        assert len(result_events) > 0, "No searchResultGenerated events logged"

        # Click on first search result
        result_link = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "a.result-link"))
        )
        result_url = result_link.get_attribute("href")

        # Store the current URL to verify we return to it
        serp_url = driver.current_url

        result_link.click()

        # Wait for navigation away from SERP
        # The click event handler logs before navigation, but we need to wait
        # for the page to actually change
        WebDriverWait(driver, 10).until(
            lambda d: d.current_url != serp_url
        )

        # Navigate back using browser back button
        driver.back()

        # Wait for page to load (either from BFCache or fresh)
        # We should be back on the SERP page now
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "article.content-section"))
        )

        # Verify we're back on the SERP
        assert "result" in driver.current_url, (
            f"Expected to be back on SERP, but URL is {driver.current_url}"
        )

        # Small delay to allow pageshow event to fire and logging to complete
        time.sleep(0.5)

        # Now we can read localStorage again (same origin)
        logs_after_back = get_session_logs(driver)

        # Verify clickedResult was logged (happened before navigation)
        click_events = [
            log for log in logs_after_back
            if log.get("type") == "clickedResult"
        ]
        assert len(click_events) > 0, (
            f"clickedResult event not logged. "
            f"Event types found: {[log.get('type') for log in logs_after_back]}"
        )

        # Check for wentBack event (should be logged on return)
        went_back_events = [
            log for log in logs_after_back
            if log.get("type") == "wentBack"
        ]

        assert len(went_back_events) > 0, (
            f"wentBack event not logged after back navigation. "
            f"Total events: {len(logs_after_back)}, "
            f"Event types: {[log.get('type') for log in logs_after_back]}"
        )

        # Verify wentBack event has correct structure
        went_back = went_back_events[0]
        assert "query" in went_back, "wentBack missing 'query' field"
        assert "fromURL" in went_back, "wentBack missing 'fromURL' field"
        assert "toURL" in went_back, "wentBack missing 'toURL' field"

        # Verify fromURL matches the result we clicked
        assert went_back["fromURL"] == result_url, (
            f"wentBack fromURL mismatch. Expected {result_url}, got {went_back['fromURL']}"
        )

    def test_no_duplicate_search_result_events_on_back(self, driver, app_url):
        """
        Test that searchResultGenerated events are NOT duplicated on back navigation.

        When returning via back button, only wentBack should be logged,
        not new searchResultGenerated events for results already logged.
        """
        # Clear state
        driver.get(app_url + "/start")
        clear_local_storage(driver)

        # Navigate through the flow (simplified - assuming session exists)
        try:
            driver.get(app_url)
            search_box = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.ID, "search-box"))
            )
        except Exception:
            pytest.skip("Could not access home page - session may be required")

        # Submit search
        search_box.clear()
        search_box.send_keys("duplicate test")
        search_box.send_keys(Keys.RETURN)

        # Wait for results
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "article.content-section"))
        )

        # Count initial searchResultGenerated events
        initial_logs = get_session_logs(driver)
        initial_result_count = len([
            log for log in initial_logs
            if log.get("type") == "searchResultGenerated"
        ])

        # Click result and go back
        result_link = driver.find_element(By.CSS_SELECTOR, "a.result-link")
        result_link.click()
        time.sleep(0.5)
        driver.back()

        # Wait for page
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "article.content-section"))
        )
        time.sleep(0.5)

        # Count searchResultGenerated events after back
        final_logs = get_session_logs(driver)
        final_result_count = len([
            log for log in final_logs
            if log.get("type") == "searchResultGenerated"
        ])

        # Should NOT have duplicate searchResultGenerated events
        assert final_result_count == initial_result_count, (
            f"searchResultGenerated events duplicated on back navigation. "
            f"Before: {initial_result_count}, After: {final_result_count}"
        )

    def test_event_listeners_not_duplicated(self, driver, app_url):
        """
        Test that event listeners are not duplicated after back navigation.

        Multiple back navigations should not cause multiple event handlers
        to fire for a single user action.
        """
        driver.get(app_url)
        clear_local_storage(driver)

        try:
            search_box = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.ID, "search-box"))
            )
        except Exception:
            pytest.skip("Could not access search page")

        # Submit search
        search_box.send_keys("listener test")
        search_box.send_keys(Keys.RETURN)

        # Wait for results
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "article.content-section"))
        )

        # Click result, go back, repeat multiple times
        for _ in range(3):
            result_link = driver.find_element(By.CSS_SELECTOR, "a.result-link")
            result_link.click()
            time.sleep(0.3)
            driver.back()
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "article.content-section"))
            )
            time.sleep(0.3)

        # Now hover over a result
        logs_before_hover = get_session_logs(driver)

        result = driver.find_element(By.CSS_SELECTOR, "article.content-section")
        webdriver.ActionChains(driver).move_to_element(result).perform()
        time.sleep(0.2)

        logs_after_hover = get_session_logs(driver)

        # Count cursorEnteredSnippet events from this hover
        hover_events_before = len([
            log for log in logs_before_hover
            if log.get("type") == "cursorEnteredSnippet"
        ])
        hover_events_after = len([
            log for log in logs_after_hover
            if log.get("type") == "cursorEnteredSnippet"
        ])

        new_hover_events = hover_events_after - hover_events_before

        # Should only have 1 new hover event, not multiple
        assert new_hover_events == 1, (
            f"Expected 1 cursorEnteredSnippet event, got {new_hover_events}. "
            f"Event listeners may be duplicated."
        )


class TestBFCacheSpecific:
    """
    Tests specifically targeting BFCache behavior.

    Note: BFCache behavior varies by browser and conditions.
    These tests may need adjustment based on the testing environment.
    """

    def test_pageshow_persisted_handling(self, driver, app_url):
        """
        Test that pageshow event with persisted=true is handled correctly.

        This test attempts to trigger BFCache restoration and verify
        the logger properly re-initializes.
        """
        driver.get(app_url)
        clear_local_storage(driver)

        try:
            search_box = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.ID, "search-box"))
            )
        except Exception:
            pytest.skip("Could not access search page")

        search_box.send_keys("bfcache test")
        search_box.send_keys(Keys.RETURN)

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "article.content-section"))
        )

        # Get session ID before navigation
        session_id_before = driver.execute_script(
            "return window.localStorage.getItem('sessionID');"
        )

        # Navigate away and back
        result_link = driver.find_element(By.CSS_SELECTOR, "a.result-link")
        result_link.click()
        time.sleep(0.5)
        driver.back()

        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "article.content-section"))
        )
        time.sleep(0.5)

        # Verify session ID is preserved (loaded from localStorage)
        session_id_after = driver.execute_script(
            "return window.studyLogger ? window.studyLogger.sessionID : null;"
        )

        assert session_id_after == session_id_before, (
            f"Session ID mismatch after back navigation. "
            f"Before: {session_id_before}, After: {session_id_after}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
