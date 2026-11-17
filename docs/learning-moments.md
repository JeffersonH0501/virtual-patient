# Learning Moments

Learning Moments replaces the active Critical Turns interface. It is independent
pedagogical feedback, not a score breakdown or an experimentally validated measure.
The TEXT_ONLY scoring logic remains unchanged; an explicit refresh reruns it
before updating the multimodal condition. Multimodal scoring retains the
same six categories, criteria, feedback contract and application mean, and now uses
the inherited EvaluationResult without requesting turn annotations.

A learning moment is a single, highly specific improvement: the one most severe
point that most likely lowered a category's score. There is no strength/improvement
type; every moment is an opportunity to improve. A moment must be grounded in
paraverbal or nonverbal evidence on its cited turns: a purely textual failure no
longer produces a moment (text may ride along only as supporting context). It must
be anchored to one specific turn (at most two consecutive turns; the validator rejects non-consecutive aliases). Prompt version `learning_moments_v21_balanced` centers the moment on HOW the student delivered that part (voice, gaze, nods, smile), not on the wording: the prior category feedback is supplied only so that the moment does not repeat it, and a moment whose only problem is vocabulary or content is not produced. Every statement must come from the cited turns only, the problem is stated in plain words as what the delivery left no room for (the criteria only guide which problem to pick and are never named in the text) and never as the patient's reaction, and routine questions are excluded.

## Generation and persistence

Generation runs once per multimodal category — interest in the patient
(`show_interest`), understanding and empathy (`show_empathy`) and communication
clarity (`speak_clearly`) — using a dedicated prompt per category under
`config/prompts/multimodal_evaluation_prompts/learning_moment_<category>.txt`.

In the automatic evaluation flow (interview completion and full-evaluation
reprocessing), moments are generated **synchronously** right after
TEXT_PLUS_MULTIMODAL is committed, reusing the same session, so they are present
together with the evaluation instead of arriving later. The evaluation is
committed before generation runs, and generation is isolated in a try/except that
only records a failed learning-moments state; it can never roll back or invalidate
the stored scores. The superuser regenerate endpoint still stages the durable
`learning_moments` job on the existing PostgreSQL queue (it is an explicit,
out-of-band action). Generation makes three independent structured LLM calls (one
per category), each using `LearningMomentOutput` and returning at most one moment
via `{"moment": {...}}` or `{"moment": null}`. Each category may contribute zero to
three moments and there is no global cap; returning nothing is the expected outcome
when no specific, severe moment exists.
The expected result per category is one moment or none.

The existing `InterviewRecordingDB.capture_config.learning_moments` JSON stores
independent status, moments, source hash, evidence hash, evaluation run ID,
generation ID, prompt version, model/provider metadata and generation time.
No database migration, new service, dependencies or media player is required.
Historical critical_turns remain readable through the legacy schema and are never
converted or displayed as Learning Moments.

Turn identifiers are unified across evaluation and learning moments: the shared
conversation formatter labels each matched turn with a short, stable alias
(`T1`, `T2`, ...) assigned in conversation order, and keeps the alias to database
UUID map outside the prompt. The model only ever sees and cites `T#` aliases; the
original UUIDs are restored before persistence. This replaces the earlier
UUID-in-prompt scheme and the separate alias remapping step.

Each category call receives a HumanMessage with explicit labeled sections:
`RESPONSE LANGUAGE`, `TRANSCRIPT` (the category-enriched conversation, with its
evidence embedded per turn exactly as in the evaluation prompt), `EVIDENCE BY TURN`
(the valid evidence keys per alias the model may cite), `CRITERIA` (that category's
clinical criteria) and `PRIOR EVALUATION` (the persisted score and feedback, as
context only). The evaluation HumanMessage wraps the same enriched conversation in
`=== CONVERSATION (START/END) ===` delimiters so transcript text is clearly data,
not instructions.

The response language is injected explicitly in two places: the per-category
prompt renders a `{response_language}` placeholder (`get_learning_moment_prompts`),
and the HumanMessage repeats it in the `RESPONSE LANGUAGE` section. Without this,
feedback defaulted to English regardless of the interview language.

The prompts require specific, grounded feedback centered on observable behavior. Vague evaluative verdicts such as "did not show
empathy", "asked basic questions" or "communicated poorly" are explicitly
forbidden; when only a vague description is possible the model must return
`{"moment": null}`. Each moment is ONE short paragraph (`text`, two sentences, at most 50 words) written as a clinical tutor would say it to the student: the first sentence links where it happened, what the voice or body did there according to that turn's evidence and the concrete problem; the second gives one concrete change. A moment must clearly stand out in a meaningful part of the conversation (never a greeting, introduction or other routine exchange); otherwise the category returns no moment. Moments are generated once per category.

The existing formatter, glossary and quality policy supply category-filtered,
human-readable evidence. Interest receives visual evidence only during patient
turns. Empathy receives listening visual evidence and student-speech level/modulation;
clarity receives student-speech temporal/modulation. Smile behavior is the only
facial description and uses `smile_activity` in the controlled evidence vocabulary.
Scores are general context, never targets for score attribution. Raw/processed
numeric features are hashed for provenance but never sent to the LLM.

The model's wording is stored as returned: there is no check of the text and no retry
(prompt version `learning_moments_v21_balanced`). The code only fills what it already
knows: the category of the call and `evidence_used`, taken from the evidence keys
present on the cited turns ("text" when there are none). A moment is skipped only
when the output does not fit the schema (missing text, more than two turns) or
cites turns that do not exist in the interview, because the interface links to them.
A skipped category never aborts the other categories or fails the job.
A failed job status is reserved for genuine technical or schema failures (a
provider error or malformed structured output), not for an unsupported citation.

## Failure, freshness and independent regeneration

States are `not_generated`, `pending`, `processing`, `completed` and `failed`.
Automatic retries reuse an active job or a completed result with the same input
hash. Superuser-only `POST /medical-interviews/{id}/learning-moments/regenerate` stages
an independent replacement without extracting media or rerunning any score, limited to interviews in the superuser's organization.
`GET /medical-interviews/{id}/learning-moments` follows recap access restrictions.
Observation/evaluation refresh blocks manual moment regeneration until ready.

Generation errors leave persisted evaluations available and retain previous valid
moments. Read-time freshness checks hide moments when transcript, observations,
criteria/prompt or source evaluation change, or observation/evaluation refresh is
pending/stale. The generator checks the source again before publishing after the
LLM call. Superseded or failed generation can be retried with the independent button.
No automatic generation is retroactively applied to historical interviews.

Only the multimodal condition displays Learning Moments, and only under the three
categories enriched with multimodal evidence: interest in the patient
(`show_interest`), understanding and empathy (`show_empathy`) and communication
clarity (`speak_clearly`). The superuser criteria dialog applies the same scope:
the Learning Moments prompt is fetched and shown only when the selected condition
is TEXT_PLUS_MULTIMODAL and the category is one of those three. It never appears in
the TEXT_ONLY condition or for general communication, completeness or open
communication. Clicking a linked turn in a moment both seeks the replay and
scrolls the recap transcript so the corresponding turn bubble is brought into
view (no animation); the active turn stays highlighted. Existing synchronized
playback seeks when media/timestamps exist; otherwise the full exchange remains readable.
Review also opens a contextual dialog with the observation, delivery, issue, recommendation,
referenced exchange and surrounding turns. Explicit badges distinguish referenced
turns from context, and the student can continue in the synchronized recap.

## Illustrative complete moment

These UUIDs are illustrative and show the persisted form; the model cited the
corresponding `T#` aliases, which are mapped back to these IDs before storage.
Generation accepts only aliases present in the current interview's transcript.

```json
{
  "id": "a736bdc4-75cc-44c4-9880-ae9b7b1b5bcd",
  "category": "show_empathy",
  "turn_ids": [
    "c12aba83-0d0b-47b9-b230-fb5c809f7eae"
  ],
  "text": "Cuando la paciente dijo que se sentía triste, respondiste enseguida y con un tono muy parejo, sin dejar una pausa para reconocerlo. Antes de seguir, haz una pausa y responde más despacio.",
  "evidence_used": ["gaze_orientation", "speech_timing"]
}
```

## Affected files and focused validation

API: per-category prompts under
`config/prompts/multimodal_evaluation_prompts/learning_moment_<category>.txt`
(with a `{response_language}` placeholder and literal JSON braces escaped),
`app/agents/prompts/learning_moments.py` (exposes `get_learning_moment_prompts`
that renders each category prompt in the response language) and
`schemas/learning_moments.py` (`LearningMomentOutput` with a single optional moment,
no type field). `app/multimodal/conversation_formatter.py` emits the shared
`T#` aliases (`alias_to_turn_id`) and alias-keyed evidence used by both flows;
`app/multimodal/learning_moments.py` renders prompts per language, builds the
labeled per-category HumanMessage (`build_category_message`, including
`RESPONSE LANGUAGE`) and no longer remaps IDs in a separate step. UI:
`TurnInterviewRecap` scrolls the linked turn bubble into view on a jump request.
Also `app/multimodal/{evaluation_service,processing_jobs}.py`,
`app/agents/evaluation_agent.py` (delimited conversation message),
`app/routers/interview_recordings.py`, focused agent tests.

UI: `EvaluationResultsPanel`, new `LearningMomentsPanel`, `ClinicalChat/index`,
`InterviewRecap`, learning-moment types/service, English/Spanish translations and
the affected component tests. Product docs and operational `doc/` record this contract.

Checks use existing Docker services: the affected API test files and, when the UI
development toolchain is available, the affected UI test files in jsdom plus
TypeScript compilation. No full regression, production build, new capture/extractor
validation or paid model call is required for this change.

Verified for the per-category migration: the backend agent and multimodal suites
pass with the generation provider mocked (one call per category, moments require
paraverbal/nonverbal evidence, no type field). Actual model grounding and Azure availability were not
empirically tested. UI lint/type/test were not run in this environment because the
running UI container exposes no Node runtime; run them where the dev toolchain is
available.
