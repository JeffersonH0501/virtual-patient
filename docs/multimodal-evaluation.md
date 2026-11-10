# Complete multimodal evaluation

Policy: `multimodal_categories_v4_score_only`, 13 October 2026. This extends the existing
interest implementation; it does not establish empirical signal accuracy,
expert agreement, or an experimental improvement.

## Conditions and evidence ownership

Both conditions contain six categories, on the inherited 0–5 scale:

| Category | TEXT_PLUS_MULTIMODAL source | Allowed evidence |
| --- | --- | --- |
| general_communication | Exact stored TEXT_ONLY result | None |
| completeness | Exact stored TEXT_ONLY result, including its special clinical-case/progress/hypothesis/verification flow | None |
| show_interest | Multimodal call when evidence is valid | Visual orientation, head feedback, Smile behavior; listening prioritized, speaking supplementary |
| show_empathy | Multimodal call when evidence is valid | Visual orientation, head feedback, Smile behavior only while listening; prosodic level/modulation only while speaking |
| speak_clearly | Multimodal call when evidence is valid | Temporal speech pattern and prosodic modulation only while speaking |
| open_communication | Exact stored TEXT_ONLY result | None |

No additional calls are made for the three copied categories. All inherited
criteria remain unchanged. `multimodal_evaluation_aspects` describes complementary
evidence, not new independently scored criteria. Smile labels describe smile
activity/activation only; no emotion or psychological state is measured directly.
Temporal measures retain their documented proxy limitations. No manual weighted
fusion is applied.

For a registered category with no valid authorized integrated label, the service
copies the exact TEXT_ONLY result instead of invoking the LLM. Partial evidence
uses valid labels and represents other allowed families as unavailable. Unknown
labels and non-OK statuses are unavailable. Mixed descriptive patterns have no
inherent negative meaning. Availability is recorded separately in
`InterviewRecordingDB.capture_config.evaluation_processing.evidence_availability`
as `available` or `unavailable_text_fallback`, together with `policy_version`.
This preserves copied score, feedback and timestamp payloads without adding
contextual feedback fields to them. The recap exposes this processing metadata.

## Canonical conversation and prompts

Completion passes exactly the same formatted messages used by TEXT_ONLY to
the multimodal service. Message IDs are added for association only; they do not
alter the inherited evaluator's rendering. The formatter associates captured
turns by `message_id` and uses message content/order, never turn transcript or
timestamp order as a replacement. Messages without a matching turn remain in
the conversation with no invented observations or UUID. Orphan turns and
speaker mismatches cannot supply evidence or Learning Moment references.

Regeneration reloads messages through the same original controller formatting
path. Completed transcripts must remain fixed for an experimental comparison;
this implementation does not add an immutable historical input archive.

The registry contains only interest, empathy and clarity and specifies allowed
families and speaking/listening roles. The formatter sends glossary descriptions
of integrated labels only, never raw/processed features, base labels, thresholds
or numeric values. Internal `smile_activity` is displayed to the evaluator
as **Smile behavior**.

Each multimodal prompt starts with the exact inherited category prompt,
including criteria, examples, score anchors and feedback instructions. An
additional evidence block and contextual interpretation rules are appended.
Scoring does not request Critical Turns or Learning Moments. The original evaluator schema and TEXT_ONLY prompts
are unchanged. The globally selected LLM and temperature 0.7 are retained.

Each enriched result validates its 0–5 score through the inherited EvaluationResult.
Independent pedagogical feedback is generated after persistence; see
[Learning Moments](learning-moments.md). Reference validity does not prove semantic grounding.

## Persistence, overall performance and refresh

The service requires a stored TEXT_ONLY evaluation with exactly the six known
categories. It evaluates only available registered categories, rejects incomplete
or duplicate LLM category output and combines generated results with exact
textual copies in the established category order. A technical LLM failure
does not produce an invented multimodal score or silently replace a previous
evaluation. The inherited text-only technical-error fallback remains unchanged
and is not valid experimental performance evidence.

`overall_score = round(sum(the six category scores) / 6, 1)` through the existing
`InterviewEvaluationController.calculate_overall_score`. The UI uses the backend
overall of the selected condition without recalculating it. Original remains the
initial selection. Both views display six categories, feedback and criteria;
only the multimodal view includes the separate Learning Moments section. Copied results receive a discreet
text-based assessment note, and unregistered categories show no multimodal
criteria section. Historical interest-only rows remain readable with their
stored null overall; they are not presented as complete or silently backfilled.

The six-category application mean includes completeness. The thesis's primary
communication outcome still excludes completeness and retains the five
communication categories/24 criteria. General communication and open
communication have zero condition differences by construction; do not interpret
them as independently rerun multimodal evaluators.

`/recording/reprocess` regenerates observations and then reevaluates the
resulting evidence. Both phases must reach a successful terminal state for the
durable job to be marked complete. `/evaluation/regenerate` reevaluates using
the saved observations. Evaluation covers available interest/empathy/clarity, copies current
TEXT_ONLY general/completeness/open (and any evidence-unavailable category),
recalculates the overall, and replaces only TEXT_PLUS_MULTIMODAL. It never
recreates or modifies TEXT_ONLY. Superuser-only access within the same organization and mutual exclusion of refresh
operations remain. Completion evaluates TEXT_ONLY once, waits for observations,
then assembles the full multimodal condition.

Technical per-turn paraverbal/nonverbal details are restricted to superusers.
The recap retains transcript, timing and media replay for other authorized roles,
but omits their technical observation payloads. Students and teachers cannot
manually refresh analysis or regenerate evaluations, even on their own interviews.

The application schema provides one row per interview and condition. Existing metrics
continue selecting TEXT_ONLY. Old partial rows become complete only when
explicitly regenerated against a complete stored control.

## Example

Illustrative six-category API payload, not a participant or measured LLM result.
Copied feedback and timestamps are identical to the corresponding TEXT_ONLY
payloads; enriched UUIDs must reference actual turns in a real interview.

```json
{
  "evaluation_condition": "TEXT_PLUS_MULTIMODAL",
  "overall_score": 3.8,
  "evaluation_results": [
    {"aspect": "general_communication", "score": 4, "feedback": "Original general feedback.", "timestamp": "2026-10-13T10:00:00"},
    {"aspect": "completeness", "score": 4.5, "feedback": "Original completeness feedback.", "timestamp": "2026-10-13T10:00:00"},
    {"aspect": "show_interest", "score": 3.5, "feedback": "Explore the stated concern before moving on.", "timestamp": "2026-10-13T10:01:00"},
    {"aspect": "show_empathy", "score": 3.5, "feedback": "Acknowledge the patient's worry explicitly.", "timestamp": "2026-10-13T10:01:00"},
    {"aspect": "speak_clearly", "score": 3, "feedback": "Explain the recommendation and explicitly check understanding.", "timestamp": "2026-10-13T10:01:00"},
    {"aspect": "open_communication", "score": 4, "feedback": "Original open communication feedback.", "timestamp": "2026-10-13T10:00:00"}
  ]
}
```

Here the six scores sum to 22.5; the existing rounded mean is 3.8.

## Validation and manual check

Use existing Docker services from the repository root:

```bash
docker compose -f docker-compose.local.yml run --rm --no-deps api python -m pytest app/agents/tests/test_complete_multimodal_evaluation.py app/agents/tests/test_multimodal_evaluation.py app/agents/tests/test_review_refresh.py app/agents/tests/test_evaluation_scale.py app/routers/tests/test_interview_completion_gate.py -q
docker compose -f docker-compose.local.yml run --rm --no-deps ui yarn exec vitest run src/components/Evaluation/EvaluationResultsPanel.test.tsx src/components/ClinicalChat/InterviewRecap.test.tsx --environment jsdom
docker compose -f docker-compose.local.yml run --rm --no-deps ui yarn exec tsc -b
```

Tests cover exact inherited prompt prefixes, full canonical transcripts with
unmatched messages, family/role allowlists, validated IDs, three LLM calls when
all evidence is available, no calls on full unavailability, six-category
persistence/mean, copying unchanged textual results, preservation during
regeneration, failure preservation and both interface conditions/criteria.
LLM calls are mocked; no audiovisual accuracy or expert agreement is claimed.

Validation for this extension: 47 targeted API tests and 14 UI tests passed;
TypeScript, affected-file ESLint and affected-module Python compilation passed.
The manuscript compiled through its existing Bash script without undefined
references/citations. Existing box warnings remain in the rubric table and
bibliography. No full regression, production build, PostgreSQL migration or real
Azure/media interview was run. The original prompt, criterion and result-schema
files were verified unchanged; tests also verify unchanged control results and
timestamps during multimodal regeneration.

## Files changed by this extension

API (paths relative to `virtual-patient-api/`):

- `app/agents/prompts/multimodal_evaluation.py`: registry, inherited prompt extensions and localized evidence metadata.
- `app/agents/evaluation_agent.py`: skip unavailable/unregistered multimodal calls; inherited textual methods unchanged.
- `app/controllers/medical_interview_controller.py`: retain message IDs in formatted data without changing textual rendering.
- `app/multimodal/conversation_formatter.py`: canonical messages and category/speaker filtering.
- `app/multimodal/evaluation_service.py`: exact copying, fallback status, six results and original overall calculation.
- `app/multimodal/reprocess.py`: preserve availability metadata during status transitions.
- `app/routers/medical_interviews.py`: pass the original completion message snapshot into enrichment.
- `app/agents/tests/test_multimodal_evaluation.py`: update existing interest/control tests.
- `app/agents/tests/test_complete_multimodal_evaluation.py`: new complete-condition contract tests.

UI (paths relative to `virtual-patient-ui/`):

- `src/components/Evaluation/EvaluationResultsPanel.tsx` and its test: six-category view, persisted overall, separate Learning Moments and textual copies.
- `src/components/Evaluation/EvaluationCriteriaTooltip.tsx`: textual criteria fallback for unregistered categories.
- `src/components/Evaluation/helpers/evaluation.ts`: preserve result subtype when ordering categories.
- `src/types/evaluation.ts`, `src/types/recording.ts`: mixed copied/enriched results and availability metadata.
- `src/i18n/locales/en.json`, `src/i18n/locales/es.json`: localized textual-assessment note.

Repository documentation: `README.md` and this file. No migration, dependency,
Docker configuration, extractor or capture changes were made by this extension.
The thesis development/protocol/contributions chapters and internal design notes
were reconciled with the implemented contract. Earlier worktree modifications
in both sibling repositories were preserved.

Manual verification with configured existing services: calibrate and conduct an
interview, finish, compare six results/overall in both views, inspect the three
enriched criteria sections and review Learning Moments. Save the original payload,
refresh evaluation and verify its score/feedback/timestamps remain unchanged.
Refresh observations separately and then evaluation to consume the new labels.
For unavailable signals, verify the category equals its original result and
recap metadata records textual fallback. This manual Azure/media check has not
been performed by the automated tests.
