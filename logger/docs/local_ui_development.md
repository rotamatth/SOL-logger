# Local SOL+ UI preview

Start Docker Desktop, then run from the repository root:

```bash
./scripts/local-ui.sh
```

Open http://localhost:7001/welcome. To restart the study flow in your browser,
open http://localhost:7001/welcome?reset=1.

The preview runs the real Flask application. Templates, static assets, and the
main Python modules are mounted from this checkout. Save an edit and refresh
the browser; Python changes reload automatically. Flask's interactive debugger
is disabled. No connection to the university server is needed.

## Files to edit

- `logger/search-app/templates/`: page markup
- `logger/search-app/static/main.css`: styles
- `logger/search-app/static/logger.js`: interaction logging
- `logger/search-app/static/images/`: images

Keep logging behavior intact when adjusting page markup and controls.

## Search and data

The preview inherits the existing search backend and local credential files
from the base Compose configuration. Real search and autocomplete still need
network access and valid Google/SerpAPI configuration; localhost does not make
those services run offline.

Study logs and Flask sessions are stored in separate Docker volumes belonging
to the `sol-ui` Compose project. The preview does not write to
`logger/logs`. The participant/topic configuration is mounted read-only from
the existing local checkout. Closing or stopping the preview preserves its
local test logs and sessions.

## Useful commands

```bash
./scripts/local-ui.sh status
./scripts/local-ui.sh logs
./scripts/local-ui.sh stop
```

If port 7001 is occupied, choose another local port:

```bash
LOCAL_UI_PORT=7003 ./scripts/local-ui.sh
```

The extra Compose file is applied only by this helper; normal university
deployment commands keep using the base configuration. The preview binds
only to the Mac's loopback interface.

Requires Docker Compose 2.24.4 or later for the explicit port override:
https://docs.docker.com/reference/compose-file/merge/#replace-value
