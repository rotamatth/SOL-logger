# Issue #6 handover

PR #23 remains Draft on `samuele/study-progress`, targeting the maintainer-selected `matthias-dev` branch. The initial confidence design is from Figma `RHTHZ6gW4n1FK8VBw5T7St`, states `11:2913` and `11:3468`.

## Completed contracts

| Requirement | Implementation and regression coverage |
| --- | --- |
| Same participant across dated sessions, date restrictions, missed sessions, TEST isolation | Existing enrollment/admission boundary; `test_study_enrollment.py`, `test_student_start_and_recovery.py`, `test_student_security.py`. |
| Resume original attempt, questions/order, phase and drafts | SQLite snapshots and revisioned first/final drafts; `test_study_progress.py`, `test_connected_first_answer.py`, draft route/browser tests and restart smoke. |
| Initial answer, explicit unknown, confidence before confirmation | Accessible radios with no default, immediate typing visibility, blank reset, separate unknown dialog. Server rejects missing/invalid assessment; `test_initial_confidence.py` and `test_initial_confidence_browser.py`. |
| Unlock search only after durable confirmation | Existing persisted guards cover search/results/viewer/autocomplete/frame probe. Drafts never unlock search. |
| Separate final answer and first-answer consultation | Existing read-only original dialog, distinct open/close events, confirmation and retry handling; `test_search_first_answer.py`, browser counterpart, `test_final_answers.py`. |
| Questions 1–3, safe next destination, recap handoff | Persisted phase changes, per-question review, reset of per-question navigation; full connected/browser three-question regressions. Welcome/ID stay outside task phases. |
| Recap-edit drafts and append-only revisions | Schema 6 internal APIs below; originals and confidence stay immutable, before/after/timestamp/context stored, CAS and idempotent request IDs prevent competing confirmations. `test_progress_history.py`. |
| Source-snapshot repeat without lost history | Schema 6 atomic repeat API below; retires source/current attempt, clones exact source task snapshot/order, retains prior originals/revisions and allocates a fresh technical/log identity. |
| Once-only events and existing FULL/per-task logs | Canonical answer/start/session events use outbox + stable receipts. Start-write failure and stale page races have regressions. Frozen non-reward event inventory is protected in `test_manual_logging_walkthrough.py`. |
| Remove rewards and migrate consumers | Removed `/reward`, reward template/media/styles/reveal events and asset-based eligibility checks. Legacy completed-task browser state migrates once to `completed_tasks`; completion/close events remain. Researcher assignment metadata remains readable. |
| SQLite durability and backup | Configurable existing database path/volumes; short transactions, `synchronous=FULL`, foreign keys and rollback journal (`DELETE`, no WAL dependency). Existing backup/restore tests plus synthetic new-process smoke. No generated database or participant data is committed. |

## Internal APIs for #9 and #15

These methods are storage primitives; this change adds no researcher reset endpoint, recap editor, PDF or save-session interface. Their future route callers must apply session/date and researcher authorization before calling storage.

- `save_recap_draft(key, target_attempt_id, question_number, answer_phase, text, expected_revision, *, editing_context)` saves an independent draft for a completed, non-retired target. `answer_phase` is `first-answer` or `final-answer`.
- `append_answer_revision(..., text, expected_revision, *, request_id, editing_context)` appends a confirmed edit. Its CAS revision is the answer's confirmed revision (0 for the original), separate from draft revision. Exact request retries return the original revision; changed payloads conflict. A matching draft becomes an inactive record with a higher revision, preventing delayed autosave resurrection. Different newer draft text is retained.
- `recap_state(key, target_attempt_id, *, editing_context)` returns original snapshots/answers, ordered revisions, active `recap_drafts` and monotonic `recap_draft_revisions` per task. Use the latter counters even when a draft is inactive. Retired targets remain readable through a valid current editing attempt.
- `editing_context` includes `study_session_id`, `attempt_id` and `technical_session_id`; storage verifies the editor belongs to the same participant/study/TEST scope and technical run. This supports a later study session editing an earlier session's answers.
- `repeat_attempt(key, source_attempt_id, *, authorized_by, request_id, technical_session_id, log_id)` requires explicit authorization provenance and fresh technical/log IDs from the future #15 admission route. It never changes source questions, answer rows, confidence or revision records. A stable request ID prevents duplicate repeats across workers/lost acknowledgements. The storage method does not grant researcher authorization itself.

Schema 5 introduced nullable first-answer confidence; schema 6 adds history/repeat tables. Upgrades preserve historical null assessments and previously queued/published event payloads. An identical historical confirmation without an assessment still returns its saved original; new typed answers always require 1/2/3.

## External acceptance boundaries

The requested #6 runtime and storage contracts are implemented. Integration of the recap editor/UI (#9) and researcher authorization controls/admission (#15) belongs to their owning issues. Existing read-only illustrated handoff is retained; PDF, save-session, MP4, layout redesign, autosave-label changes and autocomplete tuning are outside this increment.

Chromium checks and inspected screenshots cover desktop, 768×1024 and 1024×768 tablet viewports, and 320px width. A real iPad/Safari and deployment replacement require their own acceptance environment. Hosted PR checks run on the pushed revision; local process restart/backup/restore smoke does not claim a local Docker replacement test.
