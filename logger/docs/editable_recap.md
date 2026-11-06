# Editable recap and session PDF

After all three final answers, the participant can review the latest completed
attempt in each eligible session. The three columns use saved question wording
and presentation order. A column stays neutral when its session is future,
missed or incomplete. The standard space and hearing images are local static
Figma artwork. Other themes use a neutral placeholder. Set
`SOL_RECAP_BACKGROUND` to a file relative to `search-app/static` to override
the artwork for an installation.

The arrows change questions within a column. Participants can edit final
answers and expand the original in each card. The recap autosaves each draft
separately. **Salva modifiche** commits all drafts, including hidden cards.
The SQLite transaction preserves first answers and original final answers
and appends revisions with the target and editing-session context.

**Salva sessione** first uploads queued browser logs. The server commits pending
edits, an immutable PDF and completion events together in the progress database.
The PDF contains the original first answers, initial confidence and the latest
committed final answers available at that finish. It shares the progress
database's existing volume and backup process. The PDF is served as a private,
non-cacheable attachment only to the admitted participant in that session.

Successful publication exposes **Scarica PDF** and **Ricomincia l’attività**.
The second action returns to welcome, clearing the active browser state.
Selecting the same ID again preserves the completed attempt and its PDF.
An authorized repeat can create another attempt with its own PDF. If the PDF
write fails, the transaction retains the drafts. If log publication fails,
the committed PDF and events are retried using their existing receipts.

The logs retain `sessionCompleted`. `RecapAnswerEdited` identifies both the
edited answer and the session doing the edit. `studySessionFinished` records
each successful finish, and `experimentFinished` is emitted for session 3.
