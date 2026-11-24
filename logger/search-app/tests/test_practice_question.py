"""The practice question before the ID: the whole flow, and that it records nothing."""
from pathlib import Path
import importlib.util
import re
import sqlite3

import pytest

from .progress_helpers import HiddenFields
from .test_backend_privacy import backend  # noqa: F401
from .test_study_enrollment import question_set, schedule, student_modules  # noqa: F401

APP_ROOT = Path(__file__).resolve().parents[1]
RESULT = {"title": "Tipi di eruzioni", "snippet": "Effusive ed esplosive", "link": "https://volcano.invalid/eruzioni",
          "docid": "volcano-1"}
SEARCH_KEYS = ("nav_stack", "results_by_query", "search_results", "query")


@pytest.fixture
def site(student_modules):
    module = student_modules()
    schedule(module, question_set())
    searched, completed = [], []
    backend = module.search_backend
    backend.practice_engine_configured = lambda: True
    backend.search = lambda query, page, rpp, theme=None: searched.append(theme) or (query, [dict(RESULT)], 1, "none")
    backend.autocomplete = lambda query, theme=None: completed.append(theme) or (["vulcano attivo"], "vertex")
    backend.autocomplete_query_model = lambda: "search-history"
    module.searched, module.completed = searched, completed
    return module


def answer_first(client, outcome="answered", text="Lava e cenere"):
    fields = HiddenFields(client.get("/prova/domanda").text).values
    data = {**fields, "outcome": outcome, **({"text": text, "confidence": "3"} if outcome == "answered" else {})}
    return client.post("/prova/domanda", data=data)


def token(client):
    with client.session_transaction() as saved:
        return saved["practice"]["csrf"]


def finish(client, answer="Effusive, esplosive e miste"):
    return client.post("/prova/fine", data={"answer": answer, "csrf_token": token(client)})


def through_practice(client, outcome="answered"):
    assert client.get("/prova").status_code == 200
    assert answer_first(client, outcome).status_code == 303
    assert client.post("/prova/risultati", data={"query": "tipi di eruzioni"}).status_code == 200
    assert finish(client).location.endswith("/prova/finita")


def recorded(module):
    """Every place a run leaves a trace: log files, the progress database and the study's records."""
    files = [path for path in Path(module.LOG_DIR).rglob("*") if path.is_file()]
    with sqlite3.connect(module.PROGRESS.store.path) as db:
        attempts = db.execute("SELECT COUNT(*) FROM progress_attempts").fetchone()[0]
    with sqlite3.connect(module.RESEARCH_STATE.path) as db:
        study = db.execute("SELECT COUNT(*) FROM study_attempts").fetchone()[0]
    return files, attempts, study


def test_inizia_on_the_welcome_page_opens_the_practice(site):
    page = site.app.test_client().get("/welcome").text
    assert re.search(r'href="/prova" class="app-btn app-btn-warm welcome-start-btn"', page)


def test_the_practice_opens_with_its_introduction_and_no_logger(site):
    page = site.app.test_client().get("/prova").text
    assert "Facciamo una prova!" in page and "Vi sentite pronti?" in page
    assert 'href="/prova/domanda"' in page and "Iniziamo" in page
    assert "back-guard.js" in page and "/static/logger.js" not in page


@pytest.mark.parametrize("cause", ["off", "no engine"])
def test_without_the_practice_inizia_goes_straight_to_the_id_page(site, cause):
    if cause == "off":
        site.RESEARCH_STATE.save_practice({**site.RESEARCH_STATE.practice(), "enabled": False}, 0)
    else:
        site.search_backend.practice_engine_configured = lambda: False
    client = site.app.test_client()
    assert client.get("/prova").location.endswith("/start")
    assert client.get("/prova/domanda").location.endswith("/start")


def test_the_question_page_asks_the_dashboards_question_without_a_number_or_logger(site):
    page = site.app.test_client().get("/prova/domanda").text
    assert "Le eruzioni vulcaniche possono essere di diversi tipi. Sapete elencarne 3?" in page
    assert 'id="first-answer-form"' in page and 'action="/prova/domanda"' in page
    assert "first-answer-number" not in page and "<title>Prova</title>" in page
    assert "back-guard.js" in page and "/static/logger.js" not in page and "first-answer/draft" not in page


def test_a_first_answer_needs_its_stars_or_non_lo_so(site):
    client = site.app.test_client()
    fields = HiddenFields(client.get("/prova/domanda").text).values
    refused = client.post("/prova/domanda", data={**fields, "outcome": "answered", "text": "Lava"})
    assert refused.status_code == 400 and "Non lo so" in refused.text and "Lava" in refused.text
    assert client.post("/prova/domanda", data={**fields, "outcome": "answered", "text": "Lava", "csrf_token": "x",
                                               "confidence": "2"}).status_code == 403
    assert answer_first(client).status_code == 303
    saved = client.get("/prova/domanda").text
    assert "La tua prima risposta è:" in saved and "Lava e cenere" in saved
    assert 'href="/prova/cerca"' in saved and "Entra nel motore di ricerca" in saved


def test_the_search_pages_of_the_practice_use_its_own_routes_engine_and_no_logger(site):
    client = site.app.test_client()
    client.get("/prova")
    answer_first(client)
    home = client.get("/prova/cerca").text
    assert 'action="/prova/risultati"' in home and "`/prova/suggerimenti?query=" in home
    assert "practice-page.js" in home and "/static/logger.js" not in home
    assert "window.SOL_PRACTICE = true" in home and "Sapete elencarne 3?" in home
    assert "La mia prima risposta" in home
    results = client.post("/prova/risultati", data={"query": "tipi di eruzioni"}).text
    assert 'href="/prova/pagina?url=https://volcano.invalid/eruzioni' in results
    assert "fetch('/prova/fine'" in results and 'window.location.href = "/prova/finita"' in results
    assert site.searched == ["practice"]
    viewer = client.get("/prova/pagina", query_string={"url": RESULT["link"], "query": "tipi di eruzioni"}).text
    assert 'fetch("/prova/controllo-pagina" + "?url="' in viewer and "/static/logger.js" not in viewer
    assert 'href="/prova/risultati?query=tipi+di+eruzioni&amp;page=1"' in viewer
    suggestions = client.get("/prova/suggerimenti", query_string={"query": "vulc"}).get_json()
    assert suggestions["suggestions"] == ["vulcano attivo"] and site.completed == ["practice"]


def test_the_viewer_of_the_practice_shows_only_web_addresses(site):
    client = site.app.test_client()
    answer_first(client)
    assert client.get("/prova/pagina", query_string={"url": "javascript:alert(1)"}).location.endswith("/prova/cerca")


def test_the_final_answer_needs_the_practices_token_and_some_text(site):
    client = site.app.test_client()
    answer_first(client)
    assert client.post("/prova/fine", data={"answer": "Effusive", "csrf_token": "wrong"}).status_code == 403
    assert client.post("/prova/fine", data={"answer": "   ", "csrf_token": token(client)}).status_code == 400
    assert client.post("/prova/fine", data={"answer": "x" * 5001, "csrf_token": token(client)}).status_code == 400
    assert finish(client).status_code == 303
    assert finish(client).location.endswith("/prova/finita"), "a retried request finds the practice already ended"


@pytest.mark.parametrize(("outcome", "shown"), [("answered", "Lava e cenere"), ("unknown", "Non lo so")])
def test_the_last_page_shows_both_answers_on_the_volcano_and_leads_to_the_id_page(site, outcome, shown):
    client = site.app.test_client()
    through_practice(client, outcome)
    done = client.get("/prova/finita").text
    assert "Avete finito la prova!" in done and "Ora siete pronti per iniziare l’attività." in done
    assert "Cosa sapevi prima" in done and shown in done
    assert "Cosa sai adesso" in done and "Effusive, esplosive e miste" in done
    assert "images/practice/volcano.webp" in done and "/static/logger.js" not in done
    leave = HiddenFields(done).values
    assert client.post("/prova/esci", data=leave).location.endswith("/start")
    with client.session_transaction() as saved:
        assert "practice" not in saved and not any(key in saved for key in SEARCH_KEYS)
    assert client.get("/start").status_code == 200


def practice_state(client):
    with client.session_transaction() as saved:
        return dict(saved["practice"])


def change_practice(client, text="Esplosive ed effusive", confidence="2", **extra):
    data = {"csrf_token": token(client), "text": text, "confidence": confidence, **extra}
    return client.post("/prova/cambia", data=data)


def test_a_practice_non_lo_so_can_become_a_written_answer_before_the_search(site):
    client = site.app.test_client()
    client.get("/prova")
    assert answer_first(client, "unknown").status_code == 303
    saved = client.get("/prova/domanda").text
    assert 'id="first-answer-change"' in saved and 'href="/prova/domanda?change=1"' in saved
    search = client.get("/prova/cerca").text
    assert 'id="search-change-answer"' in search and 'href="/prova/domanda?change=1"' in search
    assert 'id="search-first-answer-btn"' not in search, "one button at the top right, as in a real question"
    form = client.get("/prova/domanda?change=1").text
    assert 'id="first-answer-change-cancel"' in form and 'action="/prova/cambia"' in form
    assert 'id="first-answer-unknown"' not in form, "only a written answer can replace it"
    assert change_practice(client).location.endswith("/prova/domanda")
    assert practice_state(client)["first"] == {"outcome": "answered", "text": "Esplosive ed effusive", "confidence": 2}
    saved = client.get("/prova/domanda").text
    assert "Esplosive ed effusive" in saved and 'id="first-answer-change"' not in saved
    assert 'id="search-change-answer"' not in client.get("/prova/cerca").text
    assert change_practice(client, text="Un altro").status_code == 303
    assert practice_state(client)["first"]["text"] == "Esplosive ed effusive", "only once"
    client.post("/prova/risultati", data={"query": "tipi di eruzioni"})
    assert finish(client).location.endswith("/prova/finita")
    done = client.get("/prova/finita").text
    assert "Esplosive ed effusive" in done and "Non lo so" not in done


def test_after_the_practice_search_non_lo_so_stays(site):
    client = site.app.test_client()
    client.get("/prova")
    answer_first(client, "unknown")
    results = client.post("/prova/risultati", data={"query": "tipi di eruzioni"}).text
    assert 'id="search-change-answer"' not in results and 'id="search-first-answer-btn"' in results
    assert 'id="search-change-answer"' not in client.get("/prova/cerca").text
    assert 'id="first-answer-change"' not in client.get("/prova/domanda").text
    assert 'id="first-answer-change-cancel"' not in client.get("/prova/domanda?change=1").text
    assert change_practice(client).status_code == 303
    assert practice_state(client)["first"]["outcome"] == "unknown"


@pytest.mark.parametrize(("text", "confidence"), [("", "2"), ("   ", "2"), ("Lava", ""), ("Lava", "4")])
def test_a_practice_change_needs_text_and_stars(site, text, confidence):
    client = site.app.test_client()
    client.get("/prova")
    answer_first(client, "unknown")
    response = change_practice(client, text=text, confidence=confidence)
    assert response.status_code == 400 and 'id="first-answer-change-cancel"' in response.text
    assert practice_state(client)["first"]["outcome"] == "unknown"


def test_a_practice_change_needs_the_pages_token(site):
    client = site.app.test_client()
    client.get("/prova")
    answer_first(client, "unknown")
    assert client.post("/prova/cambia", data={"csrf_token": "wrong", "text": "Lava", "confidence": "2"}).status_code == 403
    assert practice_state(client)["first"]["outcome"] == "unknown"


def test_a_written_practice_answer_offers_no_change(site):
    client = site.app.test_client()
    client.get("/prova")
    answer_first(client)
    assert 'id="first-answer-change"' not in client.get("/prova/domanda").text
    assert 'id="search-change-answer"' not in client.get("/prova/cerca").text
    assert change_practice(client).status_code == 303
    assert practice_state(client)["first"]["text"] == "Lava e cenere"


def test_a_changed_practice_records_nothing(site):
    before = recorded(site)
    client = site.app.test_client()
    client.get("/prova")
    answer_first(client, "unknown")
    change_practice(client)
    client.post("/prova/risultati", data={"query": "tipi di eruzioni"})
    finish(client)
    client.post("/prova/esci", data=HiddenFields(client.get("/prova/finita").text).values)
    assert recorded(site) == before == ([], 0, 0)


def test_a_whole_practice_records_nothing(site):
    before = recorded(site)
    client = site.app.test_client()
    through_practice(client)
    client.get("/prova/suggerimenti", query_string={"query": "vulc"})
    client.post("/prova/esci", data=HiddenFields(client.get("/prova/finita").text).values)
    assert recorded(site) == before == ([], 0, 0)


def test_the_steps_only_go_forward(site):
    client = site.app.test_client()
    assert client.get("/prova/cerca").location.endswith("/prova")
    assert client.get("/prova/finita").location.endswith("/prova")
    client.get("/prova/domanda")
    assert client.get("/prova/cerca").location.endswith("/prova/domanda")
    assert client.get("/prova").location.endswith("/prova/domanda"), "a group coming back resumes its step"
    answer_first(client)
    assert client.get("/prova").location.endswith("/prova/cerca")
    assert client.get("/prova/finita").location.endswith("/prova/cerca")
    finish(client)
    for path in ("/prova", "/prova/domanda", "/prova/cerca", "/prova/risultati"):
        assert client.get(path).location.endswith("/prova/finita"), path


def test_frame_checks_and_suggestions_need_a_practice_that_is_searching(site):
    client = site.app.test_client()
    assert client.get("/prova/controllo-pagina", query_string={"url": RESULT["link"]}).get_json()["reason"] == "no-active-search"
    assert client.get("/prova/suggerimenti", query_string={"query": "vulc"}).get_json()["suggestions"] == []
    answer_first(client)
    assert client.get("/prova/controllo-pagina", query_string={"url": "https://elsewhere.invalid/"}).get_json()["reason"] == "not-a-search-result"
    assert site.completed == []


def test_choosing_an_id_drops_the_practice(site):
    client = site.app.test_client()
    answer_first(client)
    assert client.post("/start", data={"user_id": "1"}).status_code == 302
    with client.session_transaction() as saved:
        assert "practice" not in saved and saved["user_id"] == "1"


def test_a_browser_with_a_run_never_enters_the_practice(site):
    client = site.app.test_client()
    client.post("/start", data={"user_id": "1"})
    for path in ("/prova", "/prova/domanda", "/prova/cerca", "/prova/finita"):
        response = client.get(path)
        assert response.status_code == 302 and "/prova" not in response.location, path
    assert client.post("/prova/fine", data={"answer": "x"}).status_code == 302
    assert client.get("/prova/suggerimenti", query_string={"query": "vulc"}).get_json()["suggestions"] == []
    with client.session_transaction() as saved:
        assert "practice" not in saved


def test_the_runs_search_routes_still_refuse_a_browser_in_the_practice(site):
    client = site.app.test_client()
    answer_first(client)
    for path in ("/search", "/result", "/webpage"):
        assert client.get(path).location.endswith("/welcome"), path
    assert client.get("/autocomplete", query_string={"query": "vulc"}).get_json()["suggestions"] == []
    assert site.searched == [] and site.completed == []


def test_a_practice_keeps_the_question_it_began_with(site):
    client = site.app.test_client()
    client.get("/prova/domanda")
    site.RESEARCH_STATE.save_practice({"enabled": True, "topic": "Terremoti", "question": "Come si misura un terremoto?"}, 0)
    assert "Sapete elencarne 3?" in client.get("/prova/domanda").text
    assert "Come si misura un terremoto?" in site.app.test_client().get("/prova/domanda").text


def test_the_app_and_the_backend_name_the_practice_engine_alike(backend):  # noqa: F811
    spec = importlib.util.spec_from_file_location("practice_question_names", APP_ROOT / "practice_question.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.PRACTICE_THEME == backend.PRACTICE_THEME


def test_the_server_image_contains_the_practice_module():
    copies = (APP_ROOT / "Dockerfile").read_text()
    assert re.search(r"^COPY .*\bpractice_question\.py\b", copies, re.M)
