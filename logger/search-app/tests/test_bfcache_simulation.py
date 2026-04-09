"""
Tests that simulate BFCache behavior by directly triggering pageshow events.

Since Selenium's driver.back() may not trigger actual BFCache restoration
in headless mode, these tests directly simulate the JavaScript behavior.
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
    """Return the URL of the running Flask app."""
    return base_url


def get_session_logs(driver):
    """Retrieve logged events from localStorage."""
    logs_json = driver.execute_script(
        "return window.localStorage.getItem('sessionLogs');"
    )
    if logs_json:
        return json.loads(logs_json)
    return []


def clear_local_storage(driver):
    """Clear localStorage to reset logger state."""
    driver.execute_script("window.localStorage.clear();")


def simulate_bfcache_restore(driver):
    """
    Simulate BFCache restoration by dispatching a pageshow event
    with persisted=true.
    """
    driver.execute_script("""
        // Create and dispatch a pageshow event with persisted=true
        const event = new PageTransitionEvent('pageshow', {
            persisted: true,
            bubbles: true,
            cancelable: false
        });
        window.dispatchEvent(event);
    """)


def setup_search_session(driver, app_url, test_user_id):
    """Navigate through login and search to get to results page."""
    driver.get(app_url + "/start")
    clear_local_storage(driver)

    try:
        id_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "id-box"))
        )
        id_input.send_keys(test_user_id)
        driver.find_element(By.ID, "enter-id-form").submit()
    except Exception:
        driver.get(app_url)

    search_box = WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.ID, "search-box"))
    )
    search_box.send_keys("test query")
    search_box.send_keys(Keys.RETURN)

    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "article.content-section"))
    )


class TestBFCacheSimulation:
    """Tests that simulate BFCache behavior directly."""

    def test_pageshow_persisted_triggers_logging(self, driver, app_url, test_user_id):
        """
        Test that a simulated pageshow event with persisted=true
        triggers the logger to check for back navigation.
        """
        setup_search_session(driver, app_url, test_user_id)

        # Get initial state
        initial_logs = get_session_logs(driver)
        initial_count = len(initial_logs)

        # Simulate clicking a result by adding to history
        driver.execute_script("""
            if (window.studyLogger) {
                window.studyLogger.addHistory('https://example.com/clicked-article');
            }
        """)

        # Simulate BFCache restore
        simulate_bfcache_restore(driver)
        time.sleep(0.3)

        # Check if wentBack was logged
        final_logs = get_session_logs(driver)
        went_back_events = [
            log for log in final_logs
            if log.get("type") == "wentBack"
        ]

        assert len(went_back_events) > 0, (
            f"wentBack event not logged after simulated BFCache restore. "
            f"Events: {[log.get('type') for log in final_logs]}"
        )

    def test_no_duplicate_listeners_after_multiple_bfcache_restores(
        self, driver, app_url, test_user_id
    ):
        """
        Test that multiple BFCache restores don't cause duplicate event listeners.
        """
        setup_search_session(driver, app_url, test_user_id)
        clear_local_storage(driver)
        driver.execute_script("window.studyLogger.init();")

        # Simulate multiple BFCache restores
        for i in range(5):
            # Add history entry to simulate navigation
            driver.execute_script(f"""
                if (window.studyLogger) {{
                    window.studyLogger.addHistory('https://example.com/article{i}');
                }}
            """)
            simulate_bfcache_restore(driver)
            time.sleep(0.1)

        # Clear logs and trigger a single hover
        driver.execute_script("window.localStorage.setItem('sessionLogs', '[]');")
        driver.execute_script("window.studyLogger.logs = [];")

        # Hover over a result
        result = driver.find_element(By.CSS_SELECTOR, "article.content-section")
        webdriver.ActionChains(driver).move_to_element(result).perform()
        time.sleep(0.2)

        # Check how many cursorEnteredSnippet events were logged
        logs = get_session_logs(driver)
        hover_events = [
            log for log in logs
            if log.get("type") == "cursorEnteredSnippet"
        ]

        # With proper listener deduplication, should only have 1 event
        # With the bug, would have 5+ events (one per BFCache restore)
        assert len(hover_events) <= 1, (
            f"Expected at most 1 cursorEnteredSnippet event, got {len(hover_events)}. "
            f"Event listeners are being duplicated on BFCache restore."
        )

    def test_logger_state_resyncs_on_bfcache_restore(self, driver, app_url, test_user_id):
        """
        Test that logger state is re-synced from localStorage on BFCache restore.

        When BFCache restores a page, the in-memory logger state might be stale.
        The pageshow handler should re-initialize from localStorage.
        """
        setup_search_session(driver, app_url, test_user_id)

        # Get the current session ID
        original_session_id = driver.execute_script(
            "return window.studyLogger.sessionID;"
        )

        # Simulate what happens during BFCache: modify localStorage externally
        # (as if another tab updated it)
        new_session_id = "test-session-" + str(int(time.time()))
        driver.execute_script(f"""
            window.localStorage.setItem('sessionID', '{new_session_id}');
        """)

        # The in-memory state should still have the old session ID
        in_memory_before = driver.execute_script(
            "return window.studyLogger.sessionID;"
        )
        assert in_memory_before == original_session_id, (
            "In-memory session ID should not have changed yet"
        )

        # Simulate BFCache restore - this should re-sync from localStorage
        simulate_bfcache_restore(driver)
        time.sleep(0.2)

        # Check if the logger re-initialized from localStorage
        in_memory_after = driver.execute_script(
            "return window.studyLogger.sessionID;"
        )

        # With the fix, session ID should be re-synced from localStorage
        # Without the fix, it would still have the old value
        assert in_memory_after == new_session_id, (
            f"Logger did not re-sync from localStorage on BFCache restore. "
            f"Expected {new_session_id}, got {in_memory_after}"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
