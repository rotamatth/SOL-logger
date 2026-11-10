"""Regenerate the guide's screenshots from a throwaway dashboard with demo data.

Run after changing a page the guide shows:

    python tools/capture_guide_screens.py

It needs Playwright with Chromium (requirements-browser-test.txt). Everything it creates lives
in a temporary folder and is deleted afterwards, and every name and question says DEMO. No real
study data is involved. Only the pictures in research_dashboard/static/guide/ are written.
"""
import json
from pathlib import Path
import random
import secrets
import sys
import tempfile
import threading

from flask import Flask
from playwright.sync_api import sync_playwright
from werkzeug.security import generate_password_hash
from werkzeug.serving import make_server

APP_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_ROOT))

from research_dashboard import init_dashboard, live_views, preparation_views, session_views  # noqa: E402
from research_dashboard.guide_views import GUIDE_IMAGE_SIZE, GUIDE_STEPS  # noqa: E402
from research_dashboard.state import SETTING_FIELDS, identity  # noqa: E402

PASSWORD = secrets.token_urlsafe(16)  # New on every run; the server it opens lasts only as long as the run.
OUTPUT = APP_ROOT / "research_dashboard" / "static" / "guide"
TODAY = "2026-11-05"
YEAR = "2026/2027"
QUESTIONS = ((("1", "DEMO Luna", "DEMO — Perché la Luna sembra cambiare forma?"),
              ("2", "DEMO Api", "DEMO — Come fanno le api a produrre il miele?"),
              ("3", "DEMO Radici", "DEMO — A che cosa servono le radici di una pianta?")))
SESSIONS = (  # Slots 1-3 of 4th grade exist in every new study; the others are added in order.
    ("4", 1, "DEMO · Foreste", "2026-10-01", True),
    ("4", 2, "DEMO · Fiumi", "2026-10-15", True),
    ("4", 3, "DEMO · Vulcani", TODAY, True),
    ("4", 4, "DEMO · Oceani", "2026-11-20", True),
    ("4", 5, "DEMO · Stelle", "2026-12-03", False),
    ("5", 1, "DEMO · Metalli", "2026-11-24", True),
)
TODAY_SESSION = "grade-4-session-3"


def question_set():
    return {"approved": True, "theme": "DEMO",
            "questions": [{"id": key, "topic": topic, "question": text} for key, topic, text in QUESTIONS]}


def add_sessions(state):
    settings = state.settings()
    settings["current_school_year"] = YEAR
    state.save_settings({key: settings[key] for key in SETTING_FIELDS}, settings["revision"])
    settings = state.settings()
    for grade, number, name, date, ready in SESSIONS:
        session_id = f"grade-{grade}-session-{number}"
        session = next((item for item in settings["sessions"] if item["id"] == session_id), None)
        if session is None:
            session = {"id": session_id, "grade": grade, "number": number}
            settings["sessions"].append(session)
        session.update(name=name, date=date, school_year=YEAR)
        if ready:
            session["question_set"] = question_set()
    state.save_settings({key: settings[key] for key in SETTING_FIELDS}, settings["revision"])
    return state.settings()


def task_events(generator, uid, technical, number, topic, finish, clock):
    base = {"uid": uid, "sessionID": technical, "task_number": number, "actual_topic_number": topic}
    start_minute = 2 + number * 9

    def stamp(minute, second=0):
        return f"{clock}T09:{minute:02d}:{second:02d}.000"

    events = [{**base, "type": "TaskStarted", "timestamp": stamp(start_minute)}]
    for search in range(generator.randint(1, 4)):
        events.append({**base, "type": "querySubmitted", "timestamp": stamp(start_minute, 10 + search), "query": "demo"})
        if generator.random() < 0.2:
            events.append({**base, "type": "searchNoResults", "timestamp": stamp(start_minute, 12 + search), "query": "demo"})
    for opened in range(generator.randint(0, 3)):
        events.append({**base, "type": "clickedResult", "timestamp": stamp(start_minute + 1, opened),
                       "rank": str(generator.randint(1, 6))})
        events.append({**base, "type": "webpageClosed", "timestamp": stamp(start_minute + 1, opened + 20),
                       "durationMs": generator.randint(15, 90) * 1000})
    if generator.random() < 0.15:
        events.append({**base, "type": "taskQuestionHelpClicked", "timestamp": stamp(start_minute + 2)})
    if finish:
        events.append({**base, "type": "TaskEnded", "timestamp": stamp(start_minute + generator.randint(3, 8)),
                       "answer": "DEMO"})
    return events


def add_run(state, settings, root, generator, uid, session, finished):
    """One synthetic run: its attempt, sidecar and original log files."""
    order = ["1", "2", "3"]
    generator.shuffle(order)
    log_id = f"guide-{session['number']}"
    technical = f"guide-{uid}-{session['id']}"
    stem = f"{uid}_{log_id}"
    enrolled = settings["enrollments"][YEAR][uid]
    questions = {key: text for key, _, text in QUESTIONS}
    metadata = {
        "schema_version": 1, "collection": "v2", "participant_id": uid, "technical_session_id": technical,
        "log_id": log_id, "started_at": f"{session['date']}T09:00:00.000+01:00", "experiment_date": session["date"],
        "grade_at_collection": enrolled["grade"], "school_year_at_collection": YEAR,
        "study_session_at_collection": session["id"], "assignment_source": "shared",
        "study_session_snapshot": {key: session.get(key, "") for key in ("id", "name", "date", "grade", "number", "school_year")},
        "participant_key": settings["participant_registry"][uid]["key"], "enrollment_id": enrolled["id"], "task_order": order,
        "tasks": [{"presented_number": number, "topic_id": topic, "question": questions[topic]}
                  for number, topic in enumerate(order, 1)]}
    with state.connect() as db:
        db.execute("INSERT INTO study_attempts VALUES (?,?,?,?,1)", (technical, session["id"], uid, json.dumps(metadata)))
    (root / f"{stem}.run.json").write_text(json.dumps(metadata))
    full = []
    for number, topic in enumerate(order, 1):
        if number > finished + 1:
            break
        events = task_events(generator, uid, technical, number, topic, number <= finished, session["date"])
        full.extend(events)
        (root / f"{stem}_task{number}_topic{topic}.log").write_text("".join(json.dumps(item) + "\n" for item in events))
    (root / f"{stem}_FULL.log").write_text("".join(json.dumps(item) + "\n" for item in full))


def add_demo_data(state, root):
    generator = random.Random(7)  # The same pictures on every run.
    settings = add_sessions(state)
    sessions = {item["id"]: item for item in settings["sessions"]}
    for session_id in ("grade-4-session-1", "grade-4-session-2"):
        for child in range(1, 19):
            add_run(state, settings, root, generator, str(child), sessions[session_id], 3 if child < 16 else 2)
    for child in range(1, 14):
        add_run(state, settings, root, generator, str(child), sessions[TODAY_SESSION], 3 if child < 7 else child % 3)


def capture(base, language, target):
    with sync_playwright() as runner:
        browser = runner.chromium.launch()
        width, height = GUIDE_IMAGE_SIZE
        page = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1.5).new_page()
        page.goto(f"{base}/dashboard/login?lang={language}")
        page.fill("input[type=password]", PASSWORD)
        with page.expect_navigation():
            page.keyboard.press("Enter")
        child_page = f"/dashboard/participants/study/{identity('3')}"
        shots = {
            "sessions": ("/dashboard/sessions?grade=4", None),
            "create": ("/dashboard/sessions/new?grade=4", None),
            "ids": (f"/dashboard/prepare?grade=4&year={YEAR}&session=grade-4-session-4", ".session-status-summary"),
            "questions": (f"/dashboard/prepare?grade=4&year={YEAR}&session=grade-4-session-4", "#prepare-questions"),
            "live": (f"/dashboard/sessions/{TODAY_SESSION}/live", None),
            "data": (f"/dashboard?collection=study&grade=4&school_year={YEAR}&session=grade-4-session-1", "#class-stats-heading"),
            "child": (child_page, "#trend-heading"),
            "settings": (f"/dashboard/settings/enrollment?year={YEAR}&grade=4", ".enrollment-filter-panel"),
        }
        assert set(shots) == set(GUIDE_STEPS)
        for key, (path, anchor) in shots.items():
            page.goto(base + path + ("&" if "?" in path else "?") + f"lang={language}")
            page.wait_for_load_state("networkidle")
            if key == "live":
                page.locator("details[data-child='1'] summary").click()
            if anchor:
                page.locator(anchor).evaluate("element => window.scrollTo(0, element.getBoundingClientRect().top + scrollY - 16)")
            page.wait_for_timeout(150)
            page.screenshot(path=str(target / f"{key}.jpg"), type="jpeg", quality=70)
        browser.close()


def main():
    for module in (live_views, preparation_views, session_views):
        module.zurich_today = lambda: TODAY  # Fixed, so a session is "today" whenever this runs.
    with tempfile.TemporaryDirectory(prefix="sol-guide-") as temporary:
        folder = Path(temporary)
        for name in ("state", "v2", "legacy"):
            (folder / name).mkdir()
        # A throwaway server on 127.0.0.1, and the dashboard checks its own CSRF token.
        app = Flask(__name__)  # NOSONAR
        app.config.update(SECRET_KEY=secrets.token_hex(32), RESEARCH_STATE_DIR=str(folder / "state"),
                          RESEARCH_LOG_DIR=str(folder / "v2"), RESEARCH_LEGACY_LOG_DIR=str(folder / "legacy"),
                          RESEARCH_PASSWORD_HASH=generate_password_hash(PASSWORD, method="pbkdf2:sha256:1000"),
                          RESEARCH_PASSWORD_HASH_FILE="")
        state = init_dashboard(app)
        add_demo_data(state, folder / "v2")
        server = make_server("127.0.0.1", 0, app, threaded=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            for language in ("en", "it"):
                target = OUTPUT / language
                target.mkdir(parents=True, exist_ok=True)
                capture(f"http://127.0.0.1:{server.server_port}", language, target)
                print(language, sum(item.stat().st_size for item in target.glob("*.jpg")) // 1024, "KB")
        finally:
            server.shutdown()


if __name__ == "__main__":
    main()
