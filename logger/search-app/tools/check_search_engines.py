"""Ask each theme's search engine one real question before a session. Prints no IDs or keys.

From the application container: docker compose exec search_app python tools/check_search_engines.py
The practice question's engine is asked too when it is set. Its topic can change, so pass a query
on that topic when it is not volcanoes: ... check_search_engines.py --prova-query "terremoti"
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import search_backend  # noqa: E402

PROBES = {"space": ("spazio", "Giove satelliti"), "ear": ("orecchio", "orecchio udito"),
          "constellations": ("costellazioni", "costellazione Orsa Maggiore"), "muscles": ("muscoli", "muscoli del corpo")}
PRACTICE_QUERY = "vulcano eruzione"


def domain(link):
    return link.split("://", 1)[-1].split("/", 1)[0]


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    practice_query = argv[argv.index("--prova-query") + 1] if "--prova-query" in argv[:-1] else PRACTICE_QUERY
    if search_backend.SEARCH_BACKEND != "vertex":
        print(f"The search backend is {search_backend.SEARCH_BACKEND}, not Vertex: nothing to check.")
        return 1
    if not search_backend._theme_configs:
        print("No per-theme engine is set: every run uses the single engine.")
        return 1
    failed = False
    probes = dict(PROBES)
    if search_backend.practice_engine_configured():
        probes[search_backend.PRACTICE_THEME] = ("prova", practice_query)
    else:
        print("prova: no engine set (VERTEX_PROVA_ENGINE_ID, VERTEX_PROVA_DATA_STORE_ID): the practice question is skipped.")
    for theme, (label, query) in probes.items():
        if theme != search_backend.PRACTICE_THEME and theme not in search_backend._theme_configs:
            setting = search_backend.VERTEX_THEME_SETTINGS[theme]
            print(f"{label}: no engine set (VERTEX_{setting}_ENGINE_ID, VERTEX_{setting}_DATA_STORE_ID).")
            continue
        try:
            config = search_backend.vertex_config_for(theme)
            _, results, _, _ = search_backend.vertex_search(query, 1, 10, config)
            suggestions = search_backend.vertex_autocomplete(query[:5], config)
        except Exception as error:  # Provider messages can contain credentials: name the type only.
            print(f"{label}: FAILED ({type(error).__name__})")
            failed = True
            continue
        sites = sorted({domain(result["link"]) for result in results})[:5]
        print(f"{label}: {len(results)} results for '{query}', from {', '.join(sites) or 'no site'}; "
              f"{len(suggestions)} suggestions")
        failed = failed or not results
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
