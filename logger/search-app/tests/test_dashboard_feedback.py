"""Researcher feedback of 3 November 2026: header, wording, log downloads, IDs and school years."""
import re

from .test_enrollment_controls import Controls
from .test_research_dashboard import app, archive, configure, csrf, identity, login, write_run  # noqa: F401

YEAR = "2026/2027"
PREPARE = f"/dashboard/prepare?grade=4&year={YEAR}&session=grade-4-session-1&lang=it"


def signed_in(app):
    configure(app)
    client = app.test_client()
    login(client)
    return client


def test_header_puts_language_before_logout_and_trash_moves_to_data_and_history(app):
    client = signed_in(app)
    page = client.get(PREPARE)
    header = page.text.split('<header class="site-header">')[1].split("</nav>")[0]
    assert "/dashboard/trash" not in header
    assert header.index('class="languages"') < header.index("header-separator") < header.index("data-clears-editor-recovery")
    assert header.index('data-section="settings"') < header.index('class="languages"')
    primary = page.text.split('class="header-primary"')[1].split("</nav>")[0]
    assert re.findall(r'data-section="(\w+)"', primary) == ["sessions", "history"]
    assert '<a class="header-logo" href="/dashboard/prepare' in header
    overview = client.get("/dashboard?collection=study&grade=4&lang=it")
    trash = next(link for link in Controls(overview).links if link["text"] == "Cestino")
    shown = client.get(trash["href"])
    assert shown.status_code == 200
    assert re.search(r'data-section="history"[^>]*aria-current="page"', shown.text)
    assert "&larr; Dati e storico" in shown.text


def test_log_actions_are_plain_links_and_the_view_download_says_what_it_contains(app):
    client = signed_in(app)
    write_run(app)
    page = client.get("/dashboard?collection=study&grade=4&lang=it")
    assert "•••" not in page.text
    manage = [link for link in Controls(page).links if link["text"] == "Gestisci log"]
    assert len(manage) == 1
    assert "manage=1" in manage[0]["href"]
    assert "Scarica tutti i log di questa vista" in page.text


def test_participant_run_and_log_pages_stay_under_data_and_history(app):
    client = signed_in(app)
    key = write_run(app)[0]
    run = client.get(f"/dashboard/runs/{key}?lang=it")
    source = re.search(rf'/dashboard/runs/{key}/logs/([^/"]+)/view', run.text)[1]
    for path in (f"/dashboard/participants/study/{identity('1')}?view=logs", f"/dashboard/runs/{key}",
                 f"/dashboard/runs/{key}/logs/{source}/view"):
        shown = client.get(path + ("&" if "?" in path else "?") + "lang=it")
        assert shown.status_code == 200
        assert re.search(r'data-section="history"[^>]*aria-current="page"', shown.text), path


def test_selected_runs_download_only_those_of_this_participant(app):
    client = signed_in(app)
    first = write_run(app, suffix="first")[0]
    second = write_run(app, suffix="second")[0]
    other = write_run(app, uid="2", suffix="other")[0]
    page = client.get(f"/dashboard/participants/study/{identity('1')}?view=logs&lang=en")
    assert set(re.findall(r'name="run" value="([^"]+)"', page.text)) == {first, second}
    fields = {"csrf": csrf(page), "collection": "study", "participant": identity("1")}
    assert client.post("/dashboard/exports/runs", data=fields).status_code == 400
    assert client.post("/dashboard/exports/runs", data={**fields, "run": [second, other]}).status_code == 400
    assert client.post("/dashboard/exports/runs", data={**fields, "run": [second, second]}).status_code == 400
    _, manifest = archive(client.post("/dashboard/exports/runs", data={**fields, "run": [second]}))
    assert manifest["scope"] == "runs"
    assert manifest["selection"]["run_ids"] == [second]
    assert [run["run_id"] for run in manifest["runs"]] == [second]
    assert client.post("/dashboard/exports/runs", data={**fields, "csrf": "invalid", "run": [second]}).status_code == 400


def test_saving_the_current_school_year_again_changes_nothing_and_known_years_are_listed(app):
    client = signed_in(app)
    state = app.extensions["research"]["state"]
    before = state.settings()
    page = client.get("/dashboard/settings?section=year&grade=4&lang=it")
    assert f"Anni scolastici già presenti nello studio: {YEAR}" in page.text
    response = client.post("/dashboard/settings?section=year&grade=4", data={
        "action": "save_year", "csrf": csrf(page), "revision": before["revision"], "current_school_year": YEAR})
    assert response.status_code == 302
    assert "saved_action=year_unchanged" in response.location
    assert state.settings()["revision"] == before["revision"]
    assert "This is already the current school year" in client.get(response.location).text


def test_clearer_wording_for_past_sessions_class_questions_and_recovery_copies(app):
    client = signed_in(app)
    page = client.get(PREPARE)
    assert "I bambini non possono più iniziare questa sessione" in page.text
    assert "nuovi accessi" not in page.text
    assert "Stai modificando <strong>" in page.text
    assert "Apri anno" not in page.text
    questions = client.get("/dashboard/settings/questions/grade-4-session-1?lang=it")
    assert "<h2>Domande per tutta la classe</h2>" in questions.text
    assert "condivise" not in questions.text
    assert "protette in privato" not in questions.text
    individual = client.get("/dashboard/settings/questions/grade-4-session-1?participant=1&lang=it")
    assert "&larr; Domande per tutta la classe</a>" in individual.text


def test_import_pop_up_offers_other_classes_and_enrolls_every_ticked_id(app):
    client = signed_in(app)
    state = app.extensions["research"]["state"]
    page = client.get(PREPARE)
    form = next(form for form in Controls(page).forms if "data-requires-choice" in form["attrs"])
    offered = [control["value"] for control in form["controls"] if control.get("name") == "ids"]
    assert "21" in offered  # Quinta children are offered; this class's own are not.
    assert "1" not in offered
    assert 'data-known-ids="1 2 3' in page.text
    hidden = {control["name"]: control.get("value") for control in form["controls"] if control.get("type") == "hidden"}
    review = client.post(form["attrs"]["action"], data={**hidden, "ids": ["21", "22"]})
    assert review.status_code == 200
    assert "ID 21" in review.text
    assert "ID 22" in review.text
    assert state.settings()["enrollments"][YEAR]["21"]["grade"] == "5"  # Nothing changes before confirmation.
    confirm = next(form for form in Controls(review).forms
                   if any(control.get("value") == "confirm" for control in form["controls"]))
    fields = {control["name"]: control.get("value") for control in confirm["controls"] if control.get("name")}
    done = client.post(form["attrs"]["action"], data=fields)
    assert done.status_code == 302
    assert {state.settings()["enrollments"][YEAR][uid]["grade"] for uid in ("21", "22")} == {"4"}


def test_id_search_says_where_a_hidden_id_is(app):
    client = signed_in(app)
    state = app.extensions["research"]["state"]
    from_prepare = f"/dashboard/settings/enrollment?prepare_session=grade-4-session-1&year={YEAR}&grade=4&lang=it&q="
    other = client.get(from_prepare + "21")
    assert "ID 21</strong> non è in questa classe. È iscritto in <strong>Quinta elementare · 2026/2027</strong>" in other.text
    show = next(link for link in Controls(other).links if link["text"] == "Mostra questo ID")
    assert "prepare_session" not in show["href"]
    assert "grade=5" in show["href"]
    shown = client.get(show["href"])
    assert shown.status_code == 200
    assert any(link["text"] == "Modifica iscrizione" for link in Controls(shown).links)
    assert "non è nello studio. Per aggiungerlo usa «Crea nuovi partecipanti»." in client.get(from_prepare + "999").text
    hidden = client.get(from_prepare + "1&status=inactive")
    assert "è nascosto dal filtro sullo stato. Il suo stato è: <strong>Attivo</strong>" in hidden.text
    # Only enrolled in an earlier school year: the message names that last class.
    state.change_participants("add", {"ids": ["41"], "year": "2025/2026", "grade": "4"}, state.settings()["revision"])
    absent = client.get(from_prepare + "41")
    assert "non è iscritto in questo anno scolastico. Ultima classe: <strong>Quarta elementare · 2025/2026</strong>" in absent.text
    assert "Nessun partecipante corrisponde ai filtri" not in absent.text


def test_unnamed_session_has_no_stray_dot_on_the_questions_page(app):
    client = signed_in(app)
    page = client.get("/dashboard/settings/questions/grade-4-session-1?lang=it")
    assert "<p>2026-10-01 · Europe/Zurich</p>" in page.text
