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

## Test the research dashboard

Set a local shared research password from the repository root:

```bash
./scripts/local-ui.sh password
```

The command prompts for the password without displaying it and saves its hash
for the local preview. Start the preview with `./scripts/local-ui.sh`, then open
http://localhost:7001/dashboard and sign in with that password.

For synthetic logs without completing a student experiment, run:

```bash
./scripts/local-ui.sh demo-logs
```

This adds examples for up to six IDs in each configured grade, using your saved
ID format and session dates. It includes completed and incomplete runs, repeated
runs, a completed task with an empty answer, and a completed run without final-save
confirmation. Click **Refresh saved data** to see the checkboxes and open the logs.
All generated questions, events and metadata are marked `sol-ui-demo-v1` / `DEMO`.
The files are stored only in the local preview's Docker volume; existing files and
study settings are preserved. Repeating the command does not duplicate the fixtures.

To test collection:

1. Open **Study settings** and set the relevant grade's **Session 1** date to today
   (Europe/Zurich), then save.
2. Open http://localhost:7001/welcome in another tab and start a student run
   with an existing configured ID from **1–18**. In **Study settings → Participants**,
   choose a grade and **Edit setup** to assign a question/puzzle set to additional IDs.
   **Review changes** shows readiness and roster changes without saving; saving
   makes ready IDs available in the student app immediately.
3. Submit a task answer, then return to the dashboard and select
   the **Refresh saved data** icon in the header. Interaction logs and answers reach the dashboard at
   task submission; unfinished work is not uploaded periodically.
4. Choose a grade and use **Download all [grade]** beside the grade navigation to
   download its complete history. In **All participants**, **Download a full grade**
   offers the available grades. Every ZIP includes incomplete and repeated runs.
   **Session history** can open a particular session's results, where the context
   strip offers **Download session** and **Show full history**.
5. Use **Visualize logs** in the participant list to open that participant's saved
   runs. Tick one or more participant rows and press **Download selected** to download
   their logs together in one ZIP. Checkboxes appear only for rows with saved log files.
   The participant page's session dropdown shows one session or all sessions;
   all sessions skips empty rows. Populated session rows and saved runs offer the
   same two actions. In a run/task view,
   each original file's **Visualize logs** button opens that file's events and
   **Download log** returns the original `.log` file directly. Missing data has
   no active view or download button.
   **All participants** combines grades 3–5 across all sessions. **Download selected**
   uses only the checked rows in the displayed grade/session/year; All participants
   can include multiple grades.
   **Manage logs** opens the run list, where one run can be moved to **Trash** after
   confirmation and later restored. Trashing hides it from views and downloads;
   original source files stay on disk.
6. In **Study settings → Sessions**, choose a grade once for both creation and
   history. Expand **New session**, enter a date and optional name, then press
   **Create session**. The next session number is assigned automatically; each grade
   supports up to 100 sessions. Expand a session in **Session history** to edit its
   name or date, then press **Save session**. History shows ten sessions per page,
   newest first. Existing session numbers and source files are preserved.
7. In **Study settings**, set **Current school year** for newly started runs.
   **Save school year** changes only the year. **Participants** shows the saved
   setup for one grade, with a **Need tasks** filter and ten participants per page.
   **Edit setup → Review changes → Save changes** controls the dashboard roster and
   ready student IDs. Assign a task set to IDs without complete tasks or everyone in a grade.
   Prefixes and digit padding are preserved exactly; the 3rd-grade roster is optional.
   Started runs retain their questions and rewards if settings later change.
   Historical assignment editing is hidden while that workflow is reconsidered.
   Any previously saved assignments still classify the corresponding records;
   other archived records can be inspected at
   <http://localhost:7001/dashboard?collection=legacy&grade=all> after signing in.

Local Docker volumes keep these test logs separate from the server collection
and the checkout's real archived logs. The preview's Legacy collection also
uses a local volume. See [research_dashboard.md](research_dashboard.md) for completion rules,
exports, and study settings.

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
