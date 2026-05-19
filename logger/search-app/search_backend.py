"""
Search backend abstraction for the SOL-logger search-app.

Selects between Google Vertex AI Discovery Engine (default) and a local
PyTerrier service via the SEARCH_BACKEND environment variable.

Expected API_keys.json structure:
    {
      "vertex_ai": {
        "project_number": "425294702501",
        "location": "global",
        "engine_id": "sol-test-2_1776796467056",
        "data_store_id": "datastore-sample_1776796569534",
        "language_code": "it",
        "autocomplete_query_model": "search-history"
      },
      "serp_api": {
        "api_key": "<your-serpapi-key>"
      }
    }

serp_api.api_key is the SerpAPI key used as the autocomplete fallback when
Vertex AI autocomplete fails (and on the pyterrier backend). It is optional;
if absent the fallback is disabled.
SerpAPI autocomplete fallback can be tuned with SERP_AUTOCOMPLETE_HL
(default "it"), SERP_AUTOCOMPLETE_GL (default "it"), and
SERP_AUTOCOMPLETE_CLIENT (default "gws-wiz"); all are wired through
docker-compose.yml and read once at startup. SERP_AUTOCOMPLETE_CLIENT
selects the SerpAPI google_autocomplete client: "gws-wiz" gives
google.com-search-box-style Italian suggestions; set "chrome"/"safari"
for browser-style, "gws-wiz-serp" for the SERP variant, or run with an
explicit empty value (e.g. docker compose run -e SERP_AUTOCOMPLETE_CLIENT=)
to omit the client param entirely.

NOTE: data_store_id and engine_id are different values.
  - engine_id     -> required by SearchService (search)
  - data_store_id -> required by CompletionService (autocomplete)
Both must be present in API_keys.json (or the env vars below).
autocomplete_query_model is optional and defaults to search-history, which
matches Vertex AI Search website data stores.
The vertex Ai or search agent has to be set up on google console.
"""

import os
import json
import requests
from spellchecker import SpellChecker

from google.cloud import discoveryengine_v1 as discoveryengine
from google.api_core.client_options import ClientOptions

DEFAULT_AUTOCOMPLETE_QUERY_MODEL = "search-history"
DEFAULT_SERP_AUTOCOMPLETE_HL = "it"
DEFAULT_SERP_AUTOCOMPLETE_GL = "it"
DEFAULT_SERP_AUTOCOMPLETE_CLIENT = "gws-wiz"  # SerpAPI client; "" disables, also "chrome"/"safari"/"gws-wiz-serp"
SERP_AUTOCOMPLETE_HL = os.getenv("SERP_AUTOCOMPLETE_HL", DEFAULT_SERP_AUTOCOMPLETE_HL)
SERP_AUTOCOMPLETE_GL = os.getenv("SERP_AUTOCOMPLETE_GL", DEFAULT_SERP_AUTOCOMPLETE_GL)
SERP_AUTOCOMPLETE_CLIENT = os.getenv("SERP_AUTOCOMPLETE_CLIENT", DEFAULT_SERP_AUTOCOMPLETE_CLIENT).strip()
try:
    with open("API_keys.json") as f:
        SERP_API_KEY = json.load(f).get("serp_api", {}).get("api_key")
except (FileNotFoundError, KeyError, json.JSONDecodeError):
    SERP_API_KEY = None


def serp_autocomplete_params(query):
    params = {
        "engine": "google_autocomplete",
        "q": query,
        "api_key": SERP_API_KEY,
        "hl": SERP_AUTOCOMPLETE_HL,
        "gl": SERP_AUTOCOMPLETE_GL,
        "client": "gws-wiz" ## adding client so that autocomplete suggestions are similar to what a user would get if they used Google 
    }
    if SERP_AUTOCOMPLETE_CLIENT:
        params["client"] = SERP_AUTOCOMPLETE_CLIENT
    return params


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def load_vertex_config():
    project = os.getenv('VERTEX_PROJECT_NUMBER')
    location = os.getenv('VERTEX_LOCATION', 'global')
    engine_id = os.getenv('VERTEX_ENGINE_ID')
    data_store_id = os.getenv('VERTEX_DATA_STORE_ID')
    language_code = os.getenv('VERTEX_LANGUAGE_CODE', 'it')
    autocomplete_query_model = os.getenv('VERTEX_AUTOCOMPLETE_QUERY_MODEL')

    config_path = os.path.join(os.path.dirname(__file__), 'API_keys.json')
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                cfg = json.load(f).get('vertex_ai', {})
            project = project or cfg.get('project_number')
            location = cfg.get('location', location)
            engine_id = engine_id or cfg.get('engine_id')
            data_store_id = data_store_id or cfg.get('data_store_id')
            language_code = cfg.get('language_code', language_code)
            autocomplete_query_model = (
                autocomplete_query_model
                or cfg.get('autocomplete_query_model')
            )
        except (OSError, ValueError) as e:
            print(f"[Vertex Config WARN] Could not load API_keys.json: {e}")

    autocomplete_query_model = (
        autocomplete_query_model or DEFAULT_AUTOCOMPLETE_QUERY_MODEL
    )

    return (
        project,
        location,
        engine_id,
        data_store_id,
        language_code,
        autocomplete_query_model,
    )

# ---------------------------------------------------------------------------
# Lazy client factories
# ---------------------------------------------------------------------------

def get_search_client(location):
    client_options = None
    if location and location != "global":
        client_options = ClientOptions(
            api_endpoint=f"{location}-discoveryengine.googleapis.com"
        )
    return discoveryengine.SearchServiceClient(client_options=client_options)


def get_completion_client(location):
    client_options = None
    if location and location != "global":
        client_options = ClientOptions(
            api_endpoint=f"{location}-discoveryengine.googleapis.com"
        )
    return discoveryengine.CompletionServiceClient(client_options=client_options)


# ---------------------------------------------------------------------------
# Vertex AI backend
# ---------------------------------------------------------------------------

# Always fetch up to this many results in a single Vertex call. The Flask
# route caches the full list in session and slices client-side, mirroring
# the existing PyTerrier behavior (maxres=100).
VERTEX_MAX_RESULTS = 100


def vertex_search(query, page, rpp, config):
    project, location, engine_id, _data_store_id, language_code = config[:5]

    if not project or not engine_id:
        print("[Vertex Search ERROR] Missing project_number or engine_id in config")
        return [], 0

    client = get_search_client(location)

    serving_config = (
        f"projects/{project}/locations/{location}"
        f"/collections/default_collection/engines/{engine_id}"
        f"/servingConfigs/default_search"
    )

    try:
        request = discoveryengine.SearchRequest(
            serving_config=serving_config,
            query=query,
            page_size=VERTEX_MAX_RESULTS,
            offset=0,
            query_expansion_spec=discoveryengine.SearchRequest.QueryExpansionSpec(
                condition=discoveryengine.SearchRequest.QueryExpansionSpec.Condition.AUTO,
            ),
            spell_correction_spec=discoveryengine.SearchRequest.SpellCorrectionSpec(
                mode=discoveryengine.SearchRequest.SpellCorrectionSpec.Mode.SUGGESTION_ONLY,
            ),
            language_code=language_code,
        )
        response = client.search(request)
    except Exception as e:
        print(f"[Vertex Search ERROR] {e}")
        return [], 0

    results = []
    total = response.total_size if hasattr(response, "total_size") else 0

    if response.corrected_query:
        print("Corrected query is: ", response.corrected_query)
        corrected_query = response.corrected_query
        query_correction_source = "vertex"
    else:
        # Empty corrected_query from Vertex = query needs no correction (Vertex
        # failures return early above). Trust it; do NOT run the naive
        # pyspellchecker, which mangles correct-but-rare Italian forms
        # (e.g. "vulcaniche" -> "vulcanica").
        print("No correction needed from Vertex AI")
        query_correction_source = "none"
        corrected_query = query



    for item in response.results:
        doc_data = dict(item.document.derived_struct_data)
        title = str(doc_data.get("title", ""))
        link = str(doc_data.get("link", ""))

        snippet = ""
        snippets = doc_data.get("snippets")
        if snippets:
            snippet_list = list(snippets)
            if snippet_list:
                snippet_data = dict(snippet_list[0])
                snippet = str(
                    snippet_data.get("htmlSnippet", snippet_data.get("snippet", ""))
                )
        if not snippet:
            snippet = str(doc_data.get("snippet", ""))

        displayed_link = link
        if "://" in link:
            displayed_link = link.split("://", 1)[1].split("/", 1)[0]

        thumbnail = None
        pagemap = doc_data.get("pagemap")
        if pagemap:
            pagemap_dict = dict(pagemap)
            cse_thumb = pagemap_dict.get("cse_thumbnail")
            if cse_thumb:
                thumb_list = list(cse_thumb)
                if thumb_list:
                    thumbnail = str(dict(thumb_list[0]).get("src", ""))

        results.append({
            "title": title,
            "snippet": snippet,
            "link": link,
            "displayed_link": displayed_link,
            "docid": str(item.document.id) if item.document.id else link,
            "thumbnail": thumbnail,
        })

    return corrected_query, results, total, query_correction_source


def vertex_autocomplete(query, config, max_suggestions=5):
    project, location, _engine_id, data_store_id, _language_code = config[:5]
    autocomplete_query_model = (
        config[5] if len(config) > 5 else DEFAULT_AUTOCOMPLETE_QUERY_MODEL
    )

    print("autocomplete query model: ", autocomplete_query_model)

    if not project or not data_store_id:
        print("[Vertex Autocomplete ERROR] Missing project_number or data_store_id in config")
        return []

    client = get_completion_client(location)

    data_store_path = (
        f"projects/{project}/locations/{location}"
        f"/collections/default_collection/dataStores/{data_store_id}"
    )

    try:
        fallback_flag = 0
        request = discoveryengine.CompleteQueryRequest(
            data_store=data_store_path,
            query=query,
            query_model=autocomplete_query_model,
            include_tail_suggestions=True,
        )
        response = client.complete_query(request)
        suggestions = [s.suggestion for s in response.query_suggestions][:max_suggestions]
        if (len(suggestions)==0):
            print("No autocomplete suggestions from Vertex AI, trying SERP API...")
            fallback_flag = 1
            suggestions = pyterrier_autocomplete(query, max_suggestions)
            if (len(suggestions)==0):
                print("No suggestions generated from SERP API either.")
        else:
            print("Autocomplete suggestions from Vertex AI are: ", suggestions)
        return suggestions, fallback_flag
    except Exception as e:
        print(f"[Vertex Autocomplete ERROR] {e}")
        return [], 0


# ---------------------------------------------------------------------------
# PyTerrier fallback
# ---------------------------------------------------------------------------

def pyterrier_search(query, page, rpp, db_url="http://search_engine:7002"):
    url = f"{db_url}/ranking?query={query}&rpp={VERTEX_MAX_RESULTS}"
    corrected_query = spellcheck_query(query)
    try:
        response = requests.get(url)
    except requests.ConnectionError:
        return [], 0

    if response.status_code != 200:
        return [], 0

    try:
        data = response.json()
    except ValueError:
        return [], 0

    if isinstance(data, dict):
        itemlist = data.get("itemlist", [])
    elif isinstance(data, list):
        itemlist = data
    else:
        itemlist = []

    return corrected_query, itemlist, len(itemlist), "pyspellchecker"


def pyterrier_autocomplete(query, MAX_SUGGESTIONS=5):
    # """Stub. When SEARCH_BACKEND=pyterrier, autocomplete is disabled. To enable,
    # replace this function with a loader that prefix-matches against a curated
    # suggestions file (e.g. data/autocomplete_suggestions.json) or against the
    # PyTerrier lexicon."""
    # return []
    response = requests.get(
            "https://serpapi.com/search.json",
            params=serp_autocomplete_params(query),
            timeout=5
        )

    response.raise_for_status()
    data = response.json()

    SERP_API_suggestions = [
        s["value"] for s in data.get("suggestions", [])
    ][:MAX_SUGGESTIONS]

    return SERP_API_suggestions


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

SEARCH_BACKEND = os.getenv("SEARCH_BACKEND", "vertex").lower()
_vertex_config = load_vertex_config()


def search(query, page, rpp):
    if SEARCH_BACKEND == "vertex":
        return vertex_search(query, page, rpp, _vertex_config)
    return pyterrier_search(query, page, rpp)


def autocomplete(query):
    if SEARCH_BACKEND == "vertex":
        suggestions, fallback_flag = vertex_autocomplete(query, _vertex_config)
        if fallback_flag==1:
            return suggestions, "SERP_API"
        return suggestions, "vertex"
    return pyterrier_autocomplete(query), "pyterrier"

spell = SpellChecker(language='it')
def spellcheck_query(cleaned_query):

    words = spell.split_words(cleaned_query)
    misspelled = spell.unknown(words)
    corrected_query = ''

    for word in words:
        if word in misspelled:
            corrected_word = spell.correction(word)
            if corrected_word is not None:
                word = corrected_word
        corrected_query += word
        corrected_query += ' '
        
    return corrected_query.strip()


def autocomplete_query_model():
    if SEARCH_BACKEND == "vertex":
        return (
            _vertex_config[5]
            if len(_vertex_config) > 5
            else DEFAULT_AUTOCOMPLETE_QUERY_MODEL
        )
    return None
