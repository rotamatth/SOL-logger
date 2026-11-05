"""The guide for new researchers, opened by itself on the first sign-in in each browser."""
from flask import make_response

from .dashboard import PREFIX

GUIDE_COOKIE = "sol_guide_seen"
GUIDE_COOKIE_SECONDS = 365 * 24 * 3600
# (screenshot and wording key). The images are demo data, made by tools/capture_guide_screens.py.
GUIDE_STEPS = ("sessions", "create", "ids", "questions", "live", "data", "child", "settings")
GUIDE_IMAGE_SIZE = (1200, 800)


def register_guide_routes(dash):
    @dash.bp.get("/guide")
    def guide_page():
        response = make_response(dash.page("guide", steps=GUIDE_STEPS, image_size=GUIDE_IMAGE_SIZE,
                                           research_area="guide"))
        # A shared login has no person to remember, so "seen" belongs to the browser.
        response.set_cookie(GUIDE_COOKIE, "1", max_age=GUIDE_COOKIE_SECONDS, path=PREFIX, httponly=True,
                            samesite="Lax", secure=dash.app.config["RESEARCH_COOKIE_SECURE"])
        return response
