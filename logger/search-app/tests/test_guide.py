"""The guide opens by itself once per browser, stays one click away, and shows demo pictures only."""
from pathlib import Path
import re

import pytest

from .test_research_dashboard import PASSWORD, app, configure, csrf, login  # noqa: F401
from research_dashboard.guide_views import GUIDE_COOKIE, GUIDE_IMAGE_SIZE, GUIDE_STEPS

STATIC = Path(__file__).resolve().parents[1] / "research_dashboard" / "static" / "guide"


def test_the_first_sign_in_in_a_browser_opens_the_guide_and_later_ones_do_not(app):
    client = app.test_client()
    first = login(client, lang="it")
    assert first.status_code == 302 and first.location == "/dashboard/guide?lang=it"
    page = client.get(first.location)
    assert page.status_code == 200 and "Come funziona la dashboard" in page.text
    cookie = client.get_cookie(GUIDE_COOKIE, path="/dashboard")
    assert cookie and cookie.value == "1"
    assert "HttpOnly" in page.headers["Set-Cookie"] and "SameSite=Lax" in page.headers["Set-Cookie"]
    client.post("/dashboard/logout", data={"csrf": csrf(page)})
    assert login(client).location == "/dashboard/sessions?lang=en"


def test_a_page_asked_for_by_link_wins_over_the_guide(app):
    client = app.test_client()
    destination = "/dashboard/settings?grade=4"
    page = client.get("/dashboard/login", query_string={"next": destination})
    response = client.post("/dashboard/login", data={"password": PASSWORD, "csrf": csrf(page), "next": destination})
    assert response.location == destination


def test_a_wrong_password_never_marks_the_guide_as_seen(app):
    client = app.test_client()
    assert login(client, "wrong").status_code == 401
    assert client.get_cookie(GUIDE_COOKIE, path="/dashboard") is None
    assert login(client).location == "/dashboard/guide?lang=en"


def test_the_guide_needs_sign_in(app):
    assert app.test_client().get("/dashboard/guide").status_code == 302


def test_the_secure_setting_reaches_the_guide_cookie(app):
    app.config["RESEARCH_COOKIE_SECURE"] = True
    client = app.test_client()
    login(client)
    assert "Secure" in client.get("/dashboard/guide").headers["Set-Cookie"]


@pytest.mark.parametrize("path", ["/dashboard/sessions", "/dashboard/sessions/new", "/dashboard/settings",
                                  "/dashboard?collection=study&grade=4", "/dashboard/settings/enrollment", "/dashboard/guide"])
def test_the_guide_button_is_on_every_signed_in_page(app, path):
    configure(app)
    client = app.test_client()
    login(client)
    header = client.get(path).text.split('<div class="header-utilities">')[1].split("</nav>")[0]
    assert 'class="button compact header-guide" href="/dashboard/guide' in header
    assert header.index("header-guide") < header.index('data-section="settings"') < header.index('class="languages"')


def test_the_login_page_has_no_guide_button(app):
    assert "header-guide" not in app.test_client().get("/dashboard/login").text


@pytest.mark.parametrize("language,title,button", [("en", "Sessions: your starting point", "Go to Sessions"),
                                                   ("it", "Sessioni: il punto di partenza", "Vai alle sessioni")])
def test_every_step_has_wording_and_a_picture_in_each_language(app, language, title, button):
    client = app.test_client()
    login(client)
    page = client.get(f"/dashboard/guide?lang={language}")
    assert title in page.text and button in page.text
    assert not re.search(r">guide_[a-z_]+<", page.text) and 'alt="guide_' not in page.text
    images = re.findall(r'<img src="([^"]+)" width="(\d+)" height="(\d+)"[^>]*alt="([^"]+)"', page.text)
    assert [Path(src.split("?")[0]).stem for src, _, _, _ in images] == list(GUIDE_STEPS)
    for src, width, height, _ in images:
        assert f"/guide/{language}/" in src
        assert (int(width), int(height)) == GUIDE_IMAGE_SIZE
        assert client.get(src).status_code == 200


def test_the_pictures_exist_and_stay_small_enough_to_keep_in_the_repository():
    for language in ("en", "it"):
        total = 0
        for key in GUIDE_STEPS:
            path = STATIC / language / f"{key}.jpg"
            assert path.is_file(), path
            total += path.stat().st_size
        assert total < 3 * 1024 * 1024


def test_the_guide_loads_nothing_from_elsewhere_and_has_no_inline_styles(app):
    client = app.test_client()
    login(client)
    page = client.get("/dashboard/guide").text
    assert "http://" not in page and "https://" not in page
    assert " style=" not in page and "<style" not in page and "<script>" not in page


@pytest.mark.parametrize("path, status", [("/dashboard/guide", 200), ("/dashboard/trash", 200),
                                          ("/dashboard/exports/unknown-scope", 404)])
def test_pages_without_a_study_scope_survive_the_student_apps_empty_context(app, path, status):
    # The student flow adds its own ``study_context`` to every template, None outside a run.
    app.context_processor(lambda: {"study_context": None})
    client = app.test_client()
    login(client)
    assert client.get(path).status_code == status
