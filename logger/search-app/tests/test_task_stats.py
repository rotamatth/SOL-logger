"""Task statistics are computed from synthetic events and never guess missing values."""
from research_dashboard.task_stats import (add_event, chart_columns, format_duration, merge_stats, new_stats, question_rows,
                                           session_rows, summarize)


def task(*events):
    stats = new_stats()
    for event in events:
        add_event(stats, event)
    return stats


def at(minute, second=0):
    return f"2026-11-20T09:{minute:02d}:{second:02d}.000"


FULL = (
    {"type": "TaskStarted", "timestamp": at(0)},
    {"type": "querySubmitted", "timestamp": at(0, 20)},
    {"type": "searchNoResults", "timestamp": at(0, 21)},
    {"type": "querySubmitted", "timestamp": at(1)},
    {"type": "choseAutoCompleteSuggestion", "timestamp": at(1)},
    {"type": "clickedDidYouMeanSuggestion", "timestamp": at(1, 5)},
    {"type": "clickedResult", "timestamp": at(1, 10), "rank": 1},
    {"type": "webpageClosed", "timestamp": at(2), "durationMs": 45000},
    {"type": "clickedResult", "timestamp": at(2, 5), "rank": 4},
    {"type": "webpageLoadFailed", "timestamp": at(2, 6)},
    {"type": "webpageClosed", "timestamp": at(2, 30), "durationMs": 15000},
    {"type": "taskQuestionHelpClicked", "timestamp": at(2, 35)},
    {"type": "searchError", "timestamp": at(2, 40)},
    {"type": "TaskEnded", "timestamp": at(3), "answer": "Synthetic answer"},
)


def test_a_finished_task_reports_every_figure():
    assert summarize(task(*FULL)) == {
        "events": 14, "searches": 2, "no_results": 1, "suggestions": 2, "results_opened": 2,
        "help_opened": 1, "search_errors": 1, "pages_failed": 1, "seconds": 180.0, "mean_rank": 2.5,
        "page_seconds": 60, "finished": True}


def test_unlogged_kinds_count_zero_but_unmeasurable_values_stay_empty():
    figures = summarize(task({"type": "TaskStarted", "timestamp": at(0)}))
    assert figures["events"] == 1 and figures["searches"] == 0 and figures["results_opened"] == 0
    assert figures["seconds"] is None and figures["mean_rank"] is None and figures["page_seconds"] is None
    assert figures["finished"] is False


def test_a_task_without_events_has_no_figures_at_all():
    figures = summarize(new_stats())
    assert figures["events"] is None and figures["searches"] is None and figures["finished"] is False
    assert summarize(None)["events"] is None


def test_time_runs_from_the_first_start_to_the_first_submission():
    figures = summarize(task({"type": "TaskStarted", "timestamp": at(5)}, {"type": "TaskStarted", "timestamp": at(1)},
                             {"type": "TaskEnded", "timestamp": at(6)}, {"type": "TaskEnded", "timestamp": at(9)}))
    assert figures["seconds"] == 300.0


def test_result_ranks_are_logged_as_text_by_the_student_app():
    figures = summarize(task({"type": "clickedResult", "rank": "3"}, {"type": "clickedResult", "rank": 1}))
    assert figures["mean_rank"] == 2.0


def test_the_student_app_timestamp_format_gives_a_time():
    figures = summarize(task({"type": "TaskStarted", "timestamp": "2026-11-20T09:00:00.125"},
                             {"type": "TaskEnded", "timestamp": "2026-11-20T09:02:30.125"}))
    assert figures["seconds"] == 150.0


def test_bad_values_are_ignored_instead_of_breaking_the_figures():
    figures = summarize(task(
        {"type": "TaskStarted", "timestamp": "not a date"}, {"type": "TaskEnded", "timestamp": at(1)},
        {"type": "clickedResult", "rank": "first"}, {"type": "clickedResult", "rank": True},
        {"type": "webpageClosed", "durationMs": -5}, {"type": "webpageClosed"}, {"type": None}, {}))
    assert figures["seconds"] is None and figures["mean_rank"] is None and figures["page_seconds"] is None
    assert figures["results_opened"] == 2 and figures["finished"] is True


def test_mixed_naive_and_timezone_timestamps_do_not_produce_a_time():
    figures = summarize(task({"type": "TaskStarted", "timestamp": "2026-11-20T09:00:00+01:00"},
                             {"type": "TaskEnded", "timestamp": at(1)}))
    assert figures["seconds"] is None and figures["finished"] is True


def test_merging_source_files_adds_counts_and_keeps_the_earliest_times():
    first = task({"type": "TaskStarted", "timestamp": at(2)}, {"type": "querySubmitted"})
    second = task({"type": "TaskStarted", "timestamp": at(1)}, {"type": "querySubmitted"},
                  {"type": "TaskEnded", "timestamp": at(4)})
    merged = summarize(merge_stats(first, second))
    assert merged["events"] == 5 and merged["searches"] == 2 and merged["seconds"] == 180.0
    assert merge_stats(None, second) == second and merge_stats(first, None) == first
    assert merge_stats(None, None) == new_stats()


def run(child, run_id, tasks, started="2026-11-20T09:00:00", source="shared", session=None):
    return {"id": run_id, "participant_id": child, "study_participant_id": child, "started_at": started,
            "date": "2026-11-20", "assignment_source": source, "study_session": session,
            "task_stats": {str(number): item for number, item in enumerate(tasks, 1)}}


def finished(question, seconds=60.0, searches=1, topic="t1", results=0, events=4):
    return {"topic": topic, "question": question, "finished": True, "seconds": seconds, "searches": searches,
            "results_opened": results, "events": events}


def test_class_rows_group_shuffled_questions_by_what_was_asked():
    rows = question_rows([
        run("1", "a", [finished("Why?", 60.0, 1, "t1"), finished("How?", 300.0, 5, "t2")]),
        run("2", "b", [finished("How?", 100.0, 3, "t2"), finished("Why?", 120.0, 3, "t1")]),
        run("3", "c", [finished("Why?", 180.0, 2, "t1")]),
    ], expected=20)
    by_question = {row["question"]: row for row in rows}
    assert by_question["Why?"]["finished"] == 3 and by_question["Why?"]["expected"] == 20
    assert by_question["Why?"]["seconds"] == {"median": 120, "low": 60.0, "high": 180.0}
    assert isinstance(by_question["How?"]["searches"]["median"], int)  # Shown as 4, not 4.0.
    assert by_question["Why?"]["searches"]["median"] == 2
    assert by_question["How?"]["finished"] == 2
    assert by_question["How?"]["seconds"] == {"median": 200.0, "low": 100.0, "high": 300.0}


def test_a_child_counts_once_per_question_using_the_latest_finished_run():
    rows = question_rows([
        run("1", "second", [finished("Why?", 90.0)], started="2026-11-20T10:00:00"),
        run("1", "first", [finished("Why?", 600.0)], started="2026-11-20T09:00:00"),
    ])
    assert rows[0]["finished"] == 1 and rows[0]["seconds"]["median"] == 90.0


def test_unfinished_tasks_and_unidentified_runs_are_not_counted():
    unfinished = {**finished("Why?"), "finished": False}
    assert question_rows([run("1", "a", [unfinished]), run(None, "b", [finished("Why?")])]) == []


def test_individual_questions_get_their_own_row_after_the_shared_ones():
    rows = question_rows([run("1", "a", [finished("Shared?")]),
                          run("2", "b", [finished("Only for two?", topic="t9")], source="participant")])
    assert [(row["question"], row["individual"]) for row in rows] == [("Shared?", False), ("Only for two?", True)]


def test_missing_times_stay_empty_in_the_class_row():
    rows = question_rows([run("1", "a", [finished("Why?", None)])])
    assert rows[0]["seconds"] == {"median": None, "low": None, "high": None} and rows[0]["finished"] == 1


def test_a_childs_sessions_run_oldest_first_with_totals_of_finished_tasks():
    second = {"id": "s2", "date": "2026-12-01", "number": 2}
    first = {"id": "s1", "date": "2026-11-01", "number": 1}
    rows = session_rows([
        run("1", "b", [finished("A?", 60.0, 2, results=1, events=5), finished("B?", None, 3)], session=second),
        run("1", "a", [finished("C?", 120.0, 1)], session=first),
        run("1", "c", [{**finished("D?"), "finished": False}], session={"id": "s3", "date": "2027-01-01", "number": 3}),
        run("1", "d", [finished("E?")], session=None),
    ])
    assert [row["session"]["id"] for row in rows] == ["s1", "s2"]
    assert rows[1]["finished"] == 2 and rows[1]["seconds"] == 60.0 and rows[1]["searches"] == 5
    assert rows[1]["results_opened"] == 1 and rows[1]["events"] == 9


def test_durations_read_in_minutes_and_keep_missing_values_empty():
    assert format_duration(None) == "—"
    assert format_duration(0) == "0 s"
    assert format_duration(45.4) == "45 s"
    assert format_duration(120) == "2 min"
    assert format_duration(150.2) == "2 min 30 s"


def test_chart_columns_share_one_baseline_and_scale():
    chart = chart_columns([2, 4, 8])
    assert chart["top"] == 10
    heights = [column["path"] for column in chart["columns"]]
    assert all(path.startswith("M") and path.endswith(f"V{chart['base']}Z") for path in heights)
    assert all(column["left"] + 24 <= chart["width"] for column in chart["columns"])


def test_a_missing_value_keeps_its_slot_without_drawing_a_zero():
    chart = chart_columns([3, None, 0])
    assert [bool(column["path"]) for column in chart["columns"]] == [True, False, False]
    assert [column["value"] for column in chart["columns"]] == [3, None, 0]
    assert chart_columns([None])["top"] == 5 and chart_columns([])["columns"] == []


def test_columns_stay_thin_with_few_sessions_and_never_overlap_with_many():
    wide = chart_columns([1, 2])["columns"]
    assert round(wide[1]["left"] - wide[0]["left"], 1) == 120.0
    many = chart_columns(list(range(1, 13)))["columns"]
    assert all(later["left"] - earlier["left"] >= 18 for earlier, later in zip(many, many[1:], strict=False))
