# Learning Moments

Learning Moments replaces the active Critical Turns interface. It is independent
pedagogical feedback, not a score breakdown or an experimentally validated measure.
The original TEXT_ONLY evaluator remains unchanged. Multimodal scoring retains the
same six categories, criteria, feedback contract and application mean, and now uses
the inherited EvaluationResult without requesting turn annotations.

## Generation and persistence

After committing TEXT_PLUS_MULTIMODAL, the service stages a durable
`learning_moments` job in the existing PostgreSQL queue. The job makes one separate
structured LLM call using `LearningMomentsOutput`. Its maximum is three moments
per interview; zero is valid, and strengths/improvements have no enforced quota.

The existing `InterviewRecordingDB.capture_config.learning_moments` JSON stores
independent status, moments, source hash, evidence hash, evaluation run ID,
generation ID, prompt version, model/provider metadata and generation time.
No database migration, new service, dependencies or media player is required.
Historical critical_turns remain readable through the legacy schema and are never
converted or displayed as Learning Moments.

The context uses the complete canonical transcript with associated persistent turn
IDs, the three original clinical criterion sets and their persisted multimodal
scores/feedback. Scores are general context, never targets for score attribution.
The existing formatter, glossary and quality policy supply category-filtered,
human-readable evidence. Interest receives visual evidence only during patient
turns. Empathy receives listening visual evidence and student-speech level/modulation;
clarity receives student-speech temporal/modulation. Smile behavior is the only
facial description and uses `smile_activity` in the controlled evidence vocabulary.
Raw/processed numeric features are hashed for provenance but never sent to the LLM.

Validation rejects more than three moments, unsupported categories/types, blank
observations/recommendations, duplicate IDs, IDs outside the canonical interview
and unavailable evidence families on the referenced turns. Structured validation
does not itself establish semantic grounding; the prompt requires observable,
contextual descriptions and forbids psychological inference, missing-signal
penalties, unsupported score causation and invented quota fillers.

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

Only the multimodal view displays cards. Review Moment scrolls to the first
referenced turn and highlights all related turns. Existing synchronized playback
seeks when media/timestamps exist; otherwise the full exchange remains readable.
Review also opens a contextual dialog with the observation, recommendation,
referenced exchange and surrounding turns. Explicit badges distinguish referenced
turns from context, and the student can continue in the synchronized recap.

## Illustrative complete moment

These UUIDs are illustrative; generation accepts only IDs actually present in the
current interview's canonical transcript.

```json
{
  "id": "a736bdc4-75cc-44c4-9880-ae9b7b1b5bcd",
  "category": "show_empathy",
  "type": "improvement",
  "turn_ids": [
    "c12aba83-0d0b-47b9-b230-fb5c809f7eae",
    "d8c52e58-5a90-47fb-b4c5-95e3f544f894"
  ],
  "observation": "The patient expressed concern about a serious illness; the doctor moved to another question without acknowledging it.",
  "recommendation": "Acknowledge the patient's concern before continuing with clinical questions.",
  "evidence_used": ["text"]
}
```

## Affected files and focused validation

API: `app/agents/evaluation_agent.py`, scoring prompt, new
`app/agents/prompts/learning_moments.py` and `schemas/learning_moments.py`,
`app/multimodal/{conversation_formatter,evaluation_service,processing_jobs,learning_moments}.py`,
`app/routers/interview_recordings.py`, focused agent tests.

UI: `EvaluationResultsPanel`, new `LearningMomentsPanel`, `ClinicalChat/index`,
`InterviewRecap`, learning-moment types/service, English/Spanish translations and
the affected component tests. Product docs and operational `doc/` record this contract.

Checks use existing Docker services: the two affected API test files, three affected
UI test files in jsdom, and TypeScript compilation. No full regression, production
build, new capture/extractor validation or paid model call is required for this change.

Verified: 39 API cases across the two affected files, 16 UI cases, and TypeScript
compilation passed. Existing deprecation warnings remain. The generation provider
was mocked; actual model grounding and Azure availability were not empirically tested.
