#!/usr/bin/env python3
"""Read-only QA checker for SOL Search JSONL logs."""

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path


TIMESTAMP_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}(?:[+-]\d{2}:\d{2})?$"
)

SERP_QUERY_FIELD_EVENTS = {
    "querySubmitted",
    "searchResultGenerated",
    "clickedResult",
    "cursorEnteredSnippet",
    "cursorLeftSnippet",
    "pageNavigationClicked",
    "resultExposureStarted",
    "resultExposureEnded",
    "searchNoResults",
    "generatedDidYouMean",
    "hoverOverDidYouMean",
    "clickedDidYouMeanSuggestion",
}

REQUIRED_FIELDS = {
    "idSubmitted": ("uid",),
    "querySubmitted": ("query",),
    "searchResultGenerated": ("query", "docid", "rank", "page", "url"),
    "clickedResult": ("query", "docid", "rank", "page", "url", "windowLocation", "navigationUrl"),
    "cursorEnteredSnippet": ("query", "docid", "rank", "page", "url"),
    "cursorLeftSnippet": ("query", "docid", "rank", "page", "url"),
    "pageNavigationClicked": ("clicked", "fromPage", "toPage", "targetURL"),
    "customBackButtonClicked": ("fromURL", "toURL"),
    "webpageOpened": ("url",),
    "webpageClosed": ("url", "durationMs", "exitReason"),
    "resultExposureStarted": ("query", "docid", "rank", "page", "url"),
    "resultExposureEnded": ("query", "docid", "rank", "page", "url", "durationMs", "exitReason"),
    "TaskEnded": ("answer",),
    "resourceViewStarted": ("url", "windowLocation"),
    "resourceViewEnded": ("url", "windowLocation", "dwellTimeMs", "exitReason"),
    "iframeNavigation": ("fromUrl", "toUrl", "windowLocation"),
    "iframeBackNavigation": ("fromUrl", "toUrl", "windowLocation"),
    "iframeNavigationTrackingLimited": ("reason", "url", "windowLocation"),
    "browserBackBlocked": ("url", "pathname", "fromURL", "toURL"),
}

PILOT_CHECKLIST = """
Manual pilot checklist:
- Search once, double-press Enter, confirm only one querySubmitted.
- Paginate forward/back, confirm pageNavigationClicked.toPage is numeric and targetURL is present.
- Click a resource and return with the app back button, confirm customBackButtonClicked.toURL points to the SERP.
- Use the SERP back button, confirm customBackButtonClicked.toURL points to the search page.
- Press native browser Back, confirm browserBackBlocked appears with fromURL/toURL and the current page stays in place.
- End from a resource page, confirm webpageClosed appears before TaskEnded.
- Scroll the SERP, confirm resultExposureStarted/resultExposureEnded are paired and durations are plausible.
- Try a no-result query, confirm searchNoResults has query/rawQuery/sanitizedQuery.
- Select an autocomplete value, confirm choseAutoCompleteSuggestion is logged once for that selection.
""".strip()


def warn(warnings, path, line_number, message):
    location = f"{path}:{line_number}" if line_number else str(path)
    warnings.append(f"{location}: {message}")


def parse_log(path):
    events = []
    warnings = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError as err:
                warn(warnings, path, line_number, f"invalid JSON: {err}")
                continue
            if not isinstance(event, dict):
                warn(warnings, path, line_number, "JSON line is not an object")
                continue
            event["_line"] = line_number
            events.append(event)
    return events, warnings


def event_key(event, *fields):
    return tuple(event.get(field) for field in fields)


def check_events(path, events):
    warnings = []
    previous_query_submit = None
    open_webpages = defaultdict(list)
    open_exposures = {}
    open_resource_views = []

    for event in events:
        line_number = event["_line"]
        event_type = event.get("type")

        timestamp = event.get("timestamp")
        if not timestamp or not TIMESTAMP_RE.fullmatch(str(timestamp)):
            warn(warnings, path, line_number, f"bad timestamp format: {timestamp!r}")
        elif str(timestamp).endswith("Z"):
            warn(warnings, path, line_number, "timestamp is UTC-style Z, expected local timestamp")

        for field in REQUIRED_FIELDS.get(event_type, ()):
            if field not in event or event.get(field) is None:
                warn(warnings, path, line_number, f"{event_type} missing {field}")

        if event_type in SERP_QUERY_FIELD_EVENTS:
            for field in ("rawQuery", "sanitizedQuery"):
                if field not in event:
                    warn(warnings, path, line_number, f"{event_type} missing {field}")

        if event_type == "querySubmitted":
            marker = event_key(event, "task_number", "query")
            if marker == previous_query_submit:
                warn(warnings, path, line_number, "duplicate consecutive querySubmitted for same task/query")
            previous_query_submit = marker
        else:
            previous_query_submit = None

        if event_type == "pageNavigationClicked" and event.get("toPage") is None:
            warn(warnings, path, line_number, "pageNavigationClicked.toPage is null")

        if event_type == "webpageOpened":
            open_webpages[event.get("url")].append(event)
        elif event_type == "webpageClosed":
            url = event.get("url")
            if not open_webpages[url]:
                warn(warnings, path, line_number, f"webpageClosed without matching open for {url!r}")
            else:
                open_webpages[url].pop()
            if not isinstance(event.get("durationMs"), (int, float)):
                warn(warnings, path, line_number, "webpageClosed.durationMs is not numeric")

        if event_type == "resourceViewStarted":
            open_resource_views.append(event)
        elif event_type == "resourceViewEnded":
            if not open_resource_views:
                warn(warnings, path, line_number, "resourceViewEnded without matching resourceViewStarted")
            else:
                open_resource_views.pop()
            if not isinstance(event.get("dwellTimeMs"), (int, float)):
                warn(warnings, path, line_number, "resourceViewEnded.dwellTimeMs is not numeric")

        if event_type == "resultExposureStarted":
            key = event_key(event, "task_number", "query", "page", "rank", "url")
            if key in open_exposures:
                warn(warnings, path, line_number, "resultExposureStarted duplicated before end")
            open_exposures[key] = event
        elif event_type == "resultExposureEnded":
            key = event_key(event, "task_number", "query", "page", "rank", "url")
            if key not in open_exposures:
                warn(warnings, path, line_number, "resultExposureEnded without matching start")
            else:
                del open_exposures[key]
            if not isinstance(event.get("durationMs"), (int, float)):
                warn(warnings, path, line_number, "resultExposureEnded.durationMs is not numeric")

    for url, opened in open_webpages.items():
        for event in opened:
            warn(warnings, path, event["_line"], f"webpageOpened not closed for {url!r}")

    for event in open_exposures.values():
        warn(
            warnings,
            path,
            event["_line"],
            "resultExposureStarted not ended "
            f"for page={event.get('page')!r} rank={event.get('rank')!r}",
        )

    for event in open_resource_views:
        warn(
            warnings,
            path,
            event["_line"],
            f"resourceViewStarted not ended for url={event.get('url')!r}",
        )

    return warnings


def check_path(path):
    events, warnings = parse_log(path)
    warnings.extend(check_events(path, events))
    return events, warnings


def build_parser():
    parser = argparse.ArgumentParser(
        description="Read-only QA checker for SOL Search JSONL logs.",
        epilog=PILOT_CHECKLIST,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("logs", nargs="*", type=Path, help="Log files to check.")
    parser.add_argument(
        "--checklist",
        action="store_true",
        help="Print the manual pilot checklist and exit.",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.checklist:
        print(PILOT_CHECKLIST)
        return 0

    if not args.logs:
        parser.print_help()
        return 2

    total_events = 0
    all_warnings = []
    for path in args.logs:
        if not path.exists():
            all_warnings.append(f"{path}: file does not exist")
            continue
        events, warnings = check_path(path)
        total_events += len(events)
        all_warnings.extend(warnings)
        print(f"{path}: checked {len(events)} events")

    if all_warnings:
        print("\nWarnings:")
        for message in all_warnings:
            print(f"- {message}")
        print(f"\nChecked {total_events} events with {len(all_warnings)} warning(s).")
        return 1

    print(f"\nChecked {total_events} events with no warnings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
