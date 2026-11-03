# Future research diagram contract (not implemented)

Diagrams will be immutable, versioned artifacts associated with source data, not
static images embedded in the student app. No diagram artifacts exist in this release.

A future artifact record must include:

```json
{
  "schema_version": 1,
  "artifact_id": "opaque-stable-id",
  "study_id": "sol-longitudinal",
  "collection_id": "v2",
  "participant_id": "original-exact-id",
  "study_session_id": "grade-4-session-1",
  "settings_revision": 1,
  "source_runs": [{
    "run_id": "dashboard-run-id",
    "technical_session_id": "original-technical-uuid",
    "log_id": "original-log-id",
    "tasks": [{"presented_number": 1, "topic_id": "3"}],
    "source_files": [{"source_id": "indexed-source-id", "sha256": "sha256-of-exact-source-bytes"}]
  }],
  "source_revision": "fingerprint-of-source-files-answers-and-mapping-revision",
  "generated_at": "ISO-8601 timestamp with UTC offset",
  "generator_version": "version-or-commit",
  "diagram_version": 1,
  "supersedes_artifact_id": null,
  "artifact_reference": "server-resolved-private-storage-key",
  "media_type": "image/png",
  "artifact_sha256": "sha256-of-artifact"
}
```

Unknown session identity must be represented as null, never fabricated. A diagram
may refer to one task or Full Task, but must explicitly list the source run/tasks.
If it combines multiple runs, all must be named and no run may silently replace
another. The source revision must change when any source answer/log or relevant
study-session mapping changes. Earlier diagram versions and source associations
must remain available; generation never overwrites an existing artifact.

Future artifact reads must use server-resolved identifiers through authenticated
`/dashboard` routes with the same expiry, no-store and authorization checks as data
exports. Private images must not be placed in Flask's `static` directory. Any future
generation or upload action needs explicit product approval and CSRF protection.
Exports may include only artifacts that actually exist and whose recorded source
scope is contained within the selected task/run/session/participant/grade scope.
