# Responsive desktop interface — issue #11

Autocomplete fits its form, wraps long suggestions and highlights keyboard
selection. Escape and Tab dismiss it without leaving a selected option that
Enter could submit later. Arrow keys identify and scroll the active option.

Buttons wrap long labels, pagination wraps on narrow screens, and the viewer
uses its available height. Keyboard focus has a visible ring. Answer,
confirmation and question-help dialogs use named dialog semantics and real
close buttons; Tab stays inside, Escape calls the existing close action, and
closing restores focus to the opener. The final confirmation initially focuses
the continue action.

## Connected student flow

The first and final answers autosave quietly. Failed saves and conflicts still
appear next to the answer with the retry control. In the answer dialog,
“Invia risposta e termina” and “Continua a cercare” share a row, with wrapped
labels on narrow screens. The primary action opens the existing irreversible
confirmation. The secondary action resumes search and keeps the draft.
[Figma answer dialog](https://www.figma.com/design/RHTHZ6gW4n1FK8VBw5T7St/Attivit%C3%A0-Lambertenghi-2026-2027?node-id=11-3603)

Each post-search review shows the Spazio or Orecchio clip for the question's
position in the assigned set, even when the student sees the questions in a
different order. The clip plays once, muted and inline, with the two answer cards
on it, as in the Figma's "Pieces Unlock". With reduced motion, the still stays
visible until the student starts the clip. The final recap uses the theme's
static artwork. See `child_pages_2026-11.md` for how these pages were matched to
the Figma in November 2026, and why.

The Playwright student fixture drives the app against temporary SQLite and log
storage with synthetic search results. Browser assertions cover both themes
across all three questions, all six playable clips, the recap, a lost final
submission acknowledgement and the absence of duplicate answer events. Separate
tests cover draft recovery and keyboard focus. The iPad-sized runs emulate
touch and viewport dimensions in Chromium. A physical iPad and its on-screen
keyboard still need a device check.

The merged interface passed 42 Playwright and logging tests. The separate
template fixture passed 42 layout checks, seven keyboard scenarios and touch
checks in both iPad orientations. It acknowledges background log batches so
the keyboard and touch checks can inspect the submitted events.

| Screen and viewport | Before | After |
| --- | --- | --- |
| Answer dialog, 1366×768 desktop | [Before](../../output/playwright/issue11-confirm-before-desktop.png) | [After](../../output/playwright/issue11-confirm-after-desktop.png) |
| Answer dialog, 768×1024 iPad portrait | [Before](../../output/playwright/issue11-confirm-before-ipad-portrait.png) | [After](../../output/playwright/issue11-confirm-after-ipad-portrait.png) |
| Answer dialog, 1024×768 iPad landscape | [Before](../../output/playwright/issue11-confirm-before-ipad-landscape.png) | [After](../../output/playwright/issue11-confirm-after-ipad-landscape.png) |
| Answer dialog, 320×700 narrow | [Before](../../output/playwright/issue11-confirm-before-narrow.png) | [After](../../output/playwright/issue11-confirm-after-narrow.png) |
| Post-search review, 1366×768 desktop | [Before](../../output/playwright/issue11-review-before-desktop.png) | [After](../../output/playwright/issue11-review-after-desktop.png) |
| Post-search review, 768×1024 iPad portrait | [Before](../../output/playwright/issue11-review-before-ipad-portrait.png) | [After](../../output/playwright/issue11-review-after-ipad-portrait.png) |

## Original desktop baseline

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
| Full suite at the original desktop baseline | 120 passed, 24 failed and 7 errors in WSL. [Failure inventory](desktop_interface_test_results.md) |

The preview renders the real templates, CSS and logging script with synthetic
search/autocomplete and log-save responses. It never reads or writes study
data. These checks cover the client payload, including one unchanged final
answer in `TaskEnded`, and do not validate external search or production log
persistence. Touch emulation does not validate Brave on a physical iPad or its
on-screen keyboard.

The historical run reported 21 dashboard and demo assertion failures, three
checks that needed Node in WSL, and seven Selenium setup errors from the Linux
driver exiting with code 127. The Windows logging module passed.

## Repeat the focused checks

From the repository root with Chromium and the browser test dependencies installed:

```sh
SOL_REQUIRE_BROWSER_TESTS=1 python -m pytest -q \
  logger/search-app/tests/test_first_answer_flow_browser.py \
  logger/search-app/tests/test_initial_confidence_browser.py \
  logger/search-app/tests/test_final_answer_draft_browser.py \
  logger/search-app/tests/test_logging_contract.py
```

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

Keep the PR as a draft. No review request or merge has been made.
