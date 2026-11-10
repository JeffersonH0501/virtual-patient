# Self-assessment and review visibility

Successful hypothesis submission waits for durable media and the transition to
`processing`, then navigates directly to the interview review. Replay and transcript
are available during `processing` and `completed`; active and interrupted captures
do not gain replay/evaluation access through this change.

Student and teacher owners complete a private self-assessment before receiving
automated feedback. The existing human rating editor, six-category rubric, bilingual
snapshot, 0–5 finite scores, required trimmed comments and one-decimal mean are reused.
Drafts remain partial and private. Complete submissions require all six categories;
updates preserve the initial submission timestamp. This product workflow is separate
from the study's five-category expert reference and does not establish instrument validity.

Migration `004_self_ratings` adds `self_ratings`, keyed by interview and deleted by
the interview foreign-key cascade. Teacher assignments and teacher ratings retain
their own tables. Each write locks the interview, verifies ownership and role, and
accepts only processing/completed interviews. Repeated starts reuse the same row.

Owner-only endpoints:

- `GET /medical-interviews/{id}/self-rating`: rubric, status and private results.
- `POST /medical-interviews/{id}/self-rating/start`: initialize once.
- `PUT /medical-interviews/{id}/self-rating/draft`: save partial work.
- `POST /medical-interviews/{id}/self-rating/submit`: submit/update all six categories.

`review_access.self_assessment_required` selects the owner editor. Until submission,
`can_view_assessments` is false for a finished owner interview. Scores, human ratings,
learning moments, evaluation snapshots and assessment-bearing message metadata are
protected in the API. Personal history scores and personal averages exclude unsubmitted
self-assessments. Active-session clinical summaries and required calibration/language
metadata remain available. Previous access/downloads cannot be retroactively blinded.

After submission, source buttons wrap and are horizontally centered:

| Viewer | Sources in order |
| --- | --- |
| Interview owner (student/teacher) | Automatic multimodal assessment; own self-assessment |
| Assigned teacher | Automatic multimodal assessment; own assigned assessment |
| Organization superuser | Automatic unimodal; automatic multimodal; named assigned teacher assessments |

Non-administrators cannot list other teachers' ratings. Self-assessments are not
presented as teacher assignments or expert reference ratings. Submitted authors retain
the existing inline edit flow. Pending automatic processing does not hide a submitted
human rating or reset an open private draft. The two scientific automatic conditions,
their calculation, permissions for manual reprocessing and explicit deletion/retention
policies remain unchanged.

## Unified personal and assigned history

`GET /medical-interviews` includes owned started interviews and, for teachers only,
assigned started interviews whose owner still belongs to the actor's organization.
The SQL visibility condition precedes ordering and pagination; assignments never
multiply rows. `is_assigned` distinguishes the additional blue badge and disables
owner-only deletion. Assigned rows expose no interview metadata or other teachers'
scores. Their score is the current teacher's submitted rating; owned scores and
personal averages retain their automatic multimodal/self-submission contract.

`manual_rating_status` is `pending`, `in_progress` or `submitted`, using self-ratings
for owned rows and the current teacher's assigned rating otherwise. For finished
interviews, the UI displays "Por evaluar" until that manual rating is submitted,
then "Evaluando" while the raw lifecycle remains `processing`, and "Completado"
when raw status is `completed`. The lifecycle and automatic processing are unchanged.

## Source case during manual assessment

Manual rating criteria remain visible, with a static header and no disclosure control.
The completeness category includes an underlined "View full clinical case" action
before the first criterion, using the same read-only CaseDetailsDialog/CaseRecord
as the superuser catalog. Closing the dialog preserves unsaved rating fields.

`GET /medical-interviews/{id}/clinical-case` returns the localized source case only
to the owner, an assigned teacher in the current organization, or an organization
superuser, and only while the interview is `processing` or `completed`. It does
not require prior rating submission: the source case is evidence for assessing
completeness, not an automatic assessment. Existing automatic-result blinding is
unchanged. The public/authenticated catalog still exposes simplified cases to
non-superusers; active and interrupted interviews cannot use this review endpoint.
