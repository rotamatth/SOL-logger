# Existing suite failure inventory — issue #11

Final WSL run: **120 passed, 24 failed, 7 errors**.

The same counts and failing cases were observed before the keyboard/dialog changes.
No dashboard/backend implementation files were changed by this PR.

Three logging failures are caused by Node not being installed in WSL; the full
logging module passes all 19 tests on Windows with Node available. Selenium setup
fails because the Linux chromedriver exits with code 127. The 21 dashboard/demo
assertion failures remain outside this interface change.

Command, from `logger/search-app`, in the prepared Linux Python environment:

```sh
python -m pytest tests -q --tb=short
```

## Failures

- `logger.search-app.tests.test_dashboard_filters::test_obsolete_search_and_status_urls_never_hide_participants[completed]`
- `logger.search-app.tests.test_dashboard_filters::test_obsolete_search_and_status_urls_never_hide_participants[no_data]`
- `logger.search-app.tests.test_dashboard_filters::test_obsolete_search_and_status_urls_never_hide_participants[unknown]`
- `logger.search-app.tests.test_dashboard_filters::test_obsolete_search_and_status_urls_never_hide_participants[]`
- `logger.search-app.tests.test_dashboard_filters::test_obsolete_search_and_status_urls_never_hide_participants[complete]`
- `logger.search-app.tests.test_dashboard_filters::test_row_status_still_uses_the_selected_session_and_school_year`
- `logger.search-app.tests.test_logging_contract::test_logged_event_timestamp_uses_swiss_local_time_without_timezone_suffix`
- `logger.search-app.tests.test_logging_contract::test_italian_pagination_target_parsing`
- `logger.search-app.tests.test_logging_contract::test_back_navigation_return_metadata_contract`
- `logger.search-app.tests.test_research_dashboard::test_index_uses_full_once_preserves_order_versions_and_answers`
- `logger.search-app.tests.test_research_dashboard::test_unknown_legacy_repeats_and_absent_questions`
- `logger.search-app.tests.test_research_dashboard::test_missing_empty_malformed_and_partial_records_are_distinct`
- `logger.search-app.tests.test_research_dashboard::test_pagination_escaped_content_no_arbitrary_files_and_symlinks`
- `logger.search-app.tests.test_research_dashboard::test_conflicting_participant_ids_never_enter_participant_export`
- `logger.search-app.tests.test_research_dashboard::test_export_reports_truncation_and_does_not_leak_other_tasks`
- `logger.search-app.tests.test_research_dashboard::test_missing_full_log_falls_back_without_doubling_and_index_is_rebuildable`
- `logger.search-app.tests.test_research_dashboard::test_grade_session_export_respects_grade_and_date_and_preserves_all_runs`
- `logger.search-app.tests.test_research_dashboard::test_selected_download_keeps_same_participant_id_in_different_collections_separate`
- `logger.search-app.tests.test_research_dashboard::test_grade_download_excludes_other_grades_and_global_export_is_unavailable`
- `logger.search-app.tests.test_research_dashboard::test_original_log_viewer_uses_the_selected_source_with_pagination_and_escaping`
- `logger.search-app.tests.test_research_dashboard::test_all_participants_selector_shows_both_grades_and_complete_histories`
- `logger.search-app.tests.test_research_dashboard::test_historical_grade_categories_and_downloads_preserve_both_cohorts`
- `logger.search-app.tests.test_research_dashboard::test_historical_assignments_use_exact_ids_dates_and_collection`
- `logger.search-app.tests.test_research_demo::test_demo_runs_index_as_completed_incomplete_and_repeated_without_changing_settings`

## Setup errors

- `logger.search-app.tests.test_back_navigation.TestBackNavigationLogging::test_browser_back_blocked_event_logs_destination_url`
- `logger.search-app.tests.test_back_navigation.TestBackNavigationLogging::test_no_duplicate_search_result_events_on_back`
- `logger.search-app.tests.test_back_navigation.TestBackNavigationLogging::test_event_listeners_not_duplicated`
- `logger.search-app.tests.test_back_navigation.TestBFCacheSpecific::test_pageshow_persisted_handling`
- `logger.search-app.tests.test_bfcache_simulation.TestBFCacheSimulation::test_pageshow_persisted_triggers_logging`
- `logger.search-app.tests.test_bfcache_simulation.TestBFCacheSimulation::test_no_duplicate_listeners_after_multiple_bfcache_restores`
- `logger.search-app.tests.test_bfcache_simulation.TestBFCacheSimulation::test_logger_state_resyncs_on_bfcache_restore`

The separate browser checks and physical-device limitations are documented in
[desktop_interface.md](desktop_interface.md).
