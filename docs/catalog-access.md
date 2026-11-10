# Catalog access and clinical case disclosure

## Administrative writes

Organization and personality writes require the shared `require_superuser`
dependency in `app/core/auth.py`. The user router continues exposing its imported
name for existing callers. Authentication and inactive-account checks remain in
the dependency chain.

Creating an organization remains an administrator-only namespace operation.
Updating or deactivating an existing organization additionally requires that its
ID match the administrator's organization. Personality definitions remain a
shared application catalog; their existing write operations are administrator-only.
Authenticated catalog reads retain their existing routes.

Organization response timestamps are nullable datetimes serialized as ISO 8601
strings. A failed response must not be mistaken for a rolled-back write: routers
commit before response serialization, so response validation is covered by tests.

## Clinical case responses

The clinical case catalog remains read-only. `GET /clinical-cases/{case_id}`
returns full content to administrators. Students and teachers receive only the
existing `ClinicalCaseSimplified` profile fields. The full response schema is
preserved: withheld clinical values and their translation maps use its existing
null/empty defaults.

Both `GET /medical-interviews/{id}` and `GET /medical-interviews/{id}/complete`
apply the shared response policy in `app/core/review_access.py`. Non-administrators
receive the simplified case until the interview is completed, including draft,
processing, and interrupted states. Access to the interview itself must already
be authorized. Completed owners and assigned reviewers retain the full case;
cross-organization review remains denied.

Assessment blinding is independent of case visibility. An assigned teacher can
review a completed case before submitting a rating without gaining access to
automatic results. The stored clinical case and internal patient/evaluator inputs
are never redacted or rewritten.

Regression coverage: `app/routers/tests/test_catalog_security.py` and
`app/routers/tests/test_clinical_case_disclosure.py`, together with the existing
user administration, case catalog, interview access, and teacher-grading suites.
