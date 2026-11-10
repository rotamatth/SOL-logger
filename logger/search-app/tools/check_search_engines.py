"""Ask each theme's search engine one real question before a session. Prints no IDs or keys.

From the application container: docker compose exec search_app python tools/check_search_engines.py
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import search_backend  # noqa: E402

PROBES = {"space": ("spazio", "Giove satelliti"), "ear": ("orecchio", "orecchio udito")}


def domain(link):
    return link.split("://", 1)[-1].split("/", 1)[0]


def main():
    if search_backend.SEARCH_BACKEND != "vertex":
        print(f"The search backend is {search_backend.SEARCH_BACKEND}, not Vertex: nothing to check.")
        return 1
    if not search_backend._theme_configs:
        print("No per-theme engine is set: every run uses the single engine.")
        return 1
    failed = False
    for theme, (label, query) in PROBES.items():
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
