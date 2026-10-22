# Responsive desktop interface — issue #11

The first change makes autocomplete fit the available form width, wraps long
suggestions and shows the option selected with the arrow keys. Suggestion rows
retain a minimum 44 px touch target. Search submission and interaction logging
are unchanged.

## Validation of the first change

Tested on Windows with the installed Brave executable (product version
`156.1.98.60`), using Playwright in an isolated browser profile. These are browser
viewport tests, not physical iPad tests:

| Viewport | Result |
| --- | --- |
| 320 × 568 | Long suggestion wraps; no horizontal overflow; keyboard selection visible |
| 768 × 1024 | Suggestions fit; keyboard selection visible |
| 1024 × 768 | Suggestions fit; keyboard selection visible |
| 1366 × 768 | Suggestions fit; keyboard selection visible |

The preview renders the repository's actual templates, CSS and logging script
with synthetic search/autocomplete responses. It does not validate the external
search service. The 18 existing logging-contract checks in the script entry point
of `tests/test_logging_contract.py` pass.

Before/after screenshots (the first suggestion is selected with ArrowDown):

| Viewport | Before | After |
| --- | --- | --- |
| 320 px | [Before](../../output/playwright/issue11-before-320.png) | [After](../../output/playwright/issue11-after-320.png) |
| 1366 px | [Before](../../output/playwright/issue11-before-1366.png) | [After](../../output/playwright/issue11-after-1366.png) |

## Remaining checks before review

- Welcome/ID, task introduction, search/results, answer/final confirmation and
  viewer keyboard navigation, including focus and touch behavior.
- Physical iPad and available desktop devices: record models, OS and Brave
  versions, screen sizes and orientation. A tablet viewport is not a substitute
  for testing touch input and the iPad on-screen keyboard.
- The first-answer and editable recap screens from #7/#9 when they become
  available. This issue does not implement pre-knowledge or recap features.

Keep the PR as a draft until the remaining checks and logging review are done.
