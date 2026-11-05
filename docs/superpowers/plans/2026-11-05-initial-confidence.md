# Initial confidence and Issue #6 completion

> Execution: inline, continuing the user's approved Issue #6 work.

**Goal:** Collect the child's initial confidence with their first answer, preserve it across recovery, and finish the remaining in-scope question-flow checks.

**Architecture:** Extend the existing SQLite first-answer/draft records and canonical answer outbox, keeping text, confidence and progression in the same transaction. Use the existing Flask form and native radio controls styled from Figma nodes `11:2913` and `11:3468`.

**Tech stack:** Flask/Jinja, JavaScript/CSS, SQLite, pytest, Playwright Chromium.

**Spec:** User request and GitHub Issue #6. Keep PR #23 Draft on `samuele/study-progress`; preserve its current `matthias-dev` target per maintainer comments.

## Constraints and decisions

- Prompt: “Secondo te, quanto è giusta la tua risposta?”
- Values 1/2/3 map to “Poco giusta”, “Abbastanza giusta”, “Giustissima”. No default selection.
- Show immediately for trimmed nonempty text; blank text clears and hides confidence.
- Require confidence on typed confirmation server-side; confirmed unknown has null confidence.
- Migrate historical submissions with null confidence, without inventing measurements or rewriting published events.
- Persist draft confidence with its text and revision. Reject conflicting retries, stale writes and invalid values (including booleans).
- Retain the existing phase/outcome event; add confidence to its canonical payload rather than emitting another submission event.
- Exclude #9 PDF/save-session, #11 layout/MP4/autosave labels, #13 autocomplete and #15 researcher restart UI.

## Review focus

- Upgrade an existing database with submitted originals and pending events.
- Lost acknowledgements and competing submissions with different confidence.
- Clearing text while a draft save is in flight.
- Failed confirmation keeps text and selection; unknown never submits a leftover selection.
- Resume in a fresh browser/worker without unlocking search from a draft.

## Task 1: Durable first-answer confidence

Files: `study_progress.py`, `student_progress.py`, first-answer/draft/event tests and shared setup helpers.

- [ ] Add failing tests for typed validation, atomic save/event, concurrent retry conflicts, migration and draft resume.
- [ ] Run targeted pytest and observe missing confidence behavior.
- [ ] Add nullable confidence columns in schema 5; extend `submit_first_answer(..., confidence=None)` and `save_draft(..., confidence=None)` with validation.
- [ ] Pass and restore confidence in participant routes, preserving failed POST text/selection.
- [ ] Update synthetic submissions for the new required field; run affected server tests.
- [ ] Commit with changelog.

## Task 2: Figma assessment controls and recovery

Files: `first_answer.html`, `first-answer.js`, `first-answer.css`, local Figma star assets and browser tests.

- [ ] Add failing browser checks for immediate visibility, reset, required selection, unknown and cross-browser draft restore.
- [ ] Add accessible radio options and the original Figma stars; style selected state orange.
- [ ] Include confidence in revisioned autosave, recovery buffers and acknowledgment comparison.
- [ ] Update existing browser setup to make an explicit synthetic assessment.
- [ ] Run browser regressions and inspect desktop/tablet screenshots.
- [ ] Commit with changelog.

## Task 3: Issue audit and delivery

- [ ] Audit date/resume/immutable snapshots, original answers, guards, outbox, backup, event inventory and obsolete reward consumers.
- [ ] Finish reasonable uncovered #6 requirements with focused regression tests, documenting cross-issue dependencies accurately.
- [ ] Run the complete server and required Chromium suites, Ruff, JavaScript syntax and diff checks.
- [ ] Review final diff; push focused commits and rewrite the Draft PR description with current results and remaining external acceptance limits.
