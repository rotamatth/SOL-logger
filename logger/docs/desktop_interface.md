# Responsive desktop interface — issue #11

Autocomplete fits its form, wraps long suggestions and highlights keyboard
selection. Escape and Tab dismiss it without leaving a selected option that
Enter could submit later. Arrow keys identify and scroll the active option.

Buttons wrap long labels, pagination wraps on narrow screens, and the viewer
uses its available height. Keyboard focus has a visible ring. Answer,
confirmation and question-help dialogs use named dialog semantics and real
close buttons; Tab stays inside, Escape calls the existing close action, and
closing restores focus to the opener. Confirmation initially focuses the
continue action. Existing confirmation, drafts and logging handlers remain in
use. Pre-knowledge and recap features are outside this change.

## Environment and results

Tested on a Windows desktop runner, registry build `26300`, display version
`26H2`, with the installed Brave executable (product version `156.1.98.60`),
using Playwright and isolated browser profiles. Hardware model and physical
screen size were not supplied. Reported dimensions below are browser viewports.

| Check | Result |
| --- | --- |
| Layouts | 42 combinations: welcome, ID, task, search, results and viewer at 320×568, 375×667, 768×1024, 1024×768, 1366×768, 1920×1080 and 1200×400; no horizontal page overflow; answer dialogs fit |
| Keyboard | 7 scenarios pass: welcome/ID/task entry; Escape and typed search; ArrowUp/Enter; answer validation, draft, focus and confirmation; help; viewer back; visible confirmation focus at 640×400 |
| Touch emulation | 768×1024 and 1024×768 pass: question help, suggestion tap and immediate search, single query event, answer entry and close |
| Existing logging checks | Full `test_logging_contract.py` module: 19 passed on Windows with Node available |
| Existing full suite | WSL: 120 passed, 24 failed, 7 errors. See [failure inventory](desktop_interface_test_results.md) |

The preview renders the real templates, CSS and logging script with synthetic
search/autocomplete and log-save responses. It never reads or writes study
data. These checks cover the client payload, including one unchanged final
answer in `TaskEnded`, and do not validate external search or production log
persistence. Touch emulation does not validate Brave on a physical iPad or its
on-screen keyboard.

The full-suite failures were already seen before the new keyboard/dialog work:
21 dashboard/demo assertions, 3 checks requiring Node missing in WSL, and 7
Selenium setup errors from the Linux driver exiting with code 127. Dashboard
and backend implementation files are unchanged by this PR. The same logging
module passes on Windows. Do not report the full suite as passing.

## Repeat the focused checks

Use a Python environment with the app's dependencies installed, plus pytest for
the existing Python checks. From `logger/search-app`, start the isolated fixture:

```sh
python tests/ui_fixture.py
```

From the repository root in another terminal, with Node/npm and a supported
browser installed:

```sh
npx --package @playwright/cli playwright-cli -s=issue11 open http://127.0.0.1:7002/search --browser chrome
npx --package @playwright/cli playwright-cli -s=issue11 run-code --filename logger/search-app/tests/desktop_keyboard.js
npx --package @playwright/cli playwright-cli -s=issue11 run-code --filename logger/search-app/tests/desktop_layout.js
```

For Brave, pass `--config` on `open` with a local JSON file specifying
`browser.browserName: "chromium"` and
`browser.launchOptions.executablePath` pointing at the installed Brave binary.
For the touch test, also set `browser.contextOptions.hasTouch` and `isMobile` to
`true`, open a separate session, then run
`logger/search-app/tests/touch_interface.js` with `run-code --filename`.
On Windows PowerShell, use `npx.cmd` if script execution policy blocks `npx`.

From `logger/search-app`, run the existing checks:

```sh
python -m pytest tests/test_logging_contract.py -q
python -m pytest tests -q
```

## Screenshots

First suggestion selected with ArrowDown:

| Viewport | Before | After |
| --- | --- | --- |
| 320 px | [Before](../../output/playwright/issue11-before-320.png) | [After](../../output/playwright/issue11-after-320.png) |
| 1366 px | [Before](../../output/playwright/issue11-before-1366.png) | [After](../../output/playwright/issue11-after-1366.png) |

| Current flow | 320 px | 1366 px |
| --- | --- | --- |
| Results | [Screenshot](../../output/playwright/issue11-results-320.png) | [Screenshot](../../output/playwright/issue11-results-1366.png) |
| Answer | [Screenshot](../../output/playwright/issue11-answer-320.png) | [Screenshot](../../output/playwright/issue11-answer-1366.png) |
| Confirmation | [Screenshot](../../output/playwright/issue11-confirm-320.png) | [Screenshot](../../output/playwright/issue11-confirm-1366.png) |

[Viewer with keyboard focus](../../output/playwright/issue11-viewer-1366.png).

## Remaining checks before review

- Physical iPad and available desktop targets, including MacBook if used:
  record model, OS/Brave versions, physical screen size, browser viewport and
  orientation. Check touch, on-screen keyboard and external keyboard.
- Repeat the affected flows against the configured external search service and
  verify saved logs with the existing logging walkthrough/checker.
- Check first-answer and editable recap screens from #7/#9 when available;
  those features are not implemented here.

Keep the PR as a draft. No review request or merge has been made.