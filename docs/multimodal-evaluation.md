# Complete multimodal evaluation

Policy: `multimodal_categories_v9_labels_with_minimal_counts` (the category set dates from 13 October 2026). This extends the existing
interest implementation; it does not establish empirical signal accuracy,
expert agreement, or an experimental improvement.

## Conditions and evidence ownership

Both conditions contain six categories, on the inherited 0–5 scale:

| Category | TEXT_PLUS_MULTIMODAL source | Allowed evidence |
| --- | --- | --- |
| general_communication | Exact stored TEXT_ONLY result | None |
| completeness | Exact stored TEXT_ONLY result, including its special clinical-case/progress/hypothesis/verification flow | None |
| show_interest | Multimodal call when evidence is valid | Visual orientation, head feedback, Smile behavior, only while the patient speaks (doctor listening) |
| show_empathy | Multimodal call when evidence is valid | All six families (visual orientation, head feedback, smile behavior, temporal pattern, prosodic level and modulation), read in the emotional context of the conversation |
| speak_clearly | Multimodal call when evidence is valid | Temporal speech pattern, prosodic level and modulation, only while speaking |
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
families and speaking/listening roles. The formatter sends observational descriptions
of integrated labels, the verified analysis-window duration and only the gaze
percentage, nod count and nonzero internal-pause count described below. It never
sends raw series, base labels or band thresholds. Internal `smile_activity` is displayed to the evaluator
as **Smile behavior**.

The scoring prompt of each multimodal category is the inherited TEXT_ONLY prompt
(criteria, examples, score anchors and feedback instruction) with ONE block inserted
before its `Instructions:` line (`config/prompts/multimodal_evaluation_prompts/evidence_<category>.txt`).
The block describes the evidence and how to read it; removing it returns the text-only
prompt exactly, which a test verifies. The score call also uses the same user message and
the same structured output as the TEXT_ONLY call, so the two conditions differ only in the
evidence. Scoring does not request Critical Turns or Learning Moments. The evaluation
model is `gpt-4.1` for both conditions and the temperature is 0.7.

### Per-turn evidence representation

Only the text sent to the model is shaped; the persisted measurements, thresholds, labels and extractors are unchanged, and the run snapshot still stores the raw evidence of every turn. The same enriched transcript reaches the scoring call, the comment call and the learning moments.

- **Header.** A turn the category reads evidence for is headed `[TURN T4 speaker=DOCTOR duration=13.3s]`. The duration is the analysed window (`end_ms - start_ms` of the stored turn, identical to the extractors' `turn_duration_ms`): the student's speech from its onset, or the patient's confirmed TTS playback, so waiting for the reply is never included. It is omitted when the timing is not `measured`, the source is not `turn_media`/`tts_playback`, or the window does not run forward. Turns a category receives no evidence for (the student's turns for interest, the patient's turns for clarity) do not carry it. It is stated once and not repeated per family.
- **Minimal numeric evidence.** Beyond the header duration, only three measurements are sent: the gaze percentage of analysed time oriented toward the interaction area or calibrated camera (whole percentages, `<1%` for a trace), the nod count (`1 head nod` / `3 head nods`) and the count of internal pauses of at least 500 ms, only when nonzero. The integrated-label description is the main representation. No words per minute, median pause duration, smile percentage, pause-time percentage, F0 values or loudness values are sent. Nod/smile absence remains neutral and is omitted as evidence.
- **Quality notes.** Closed eyes and a missing face are mentioned qualitatively only when each accounts for at least 0.5 s: for example, `The time away includes closed eyes.` Their durations are not sent. Existing truncated-audio and speech-at-window-boundary notes are preserved.
- **Relative bands.** Descriptions no longer cite P25/P75, "provisional bands" or "defined typical ranges". Loudness is compared with the same student's other analysed turns in the interview, other bands are called descriptive, and each evidence block of the prompt says that none is a clinical norm or target.
- **Traceability.** This representation is versioned as `multimodal_categories_v9_labels_with_minimal_counts`; it does not change the glossary, persisted measurements or extraction methodology. The learning-moment source hash includes the rendered transcript. Previously saved moments whose rendered input changes are therefore stale until regenerated; this change does not regenerate them or alter stored scores automatically.

### Category comment (second call, does not score)

The comment shown for each multimodal category is written by a second call
(`category_feedback.txt`, recorded as `<category>_feedback` in the run snapshot) that receives
the conversation with its evidence and the score already assigned, and cannot change it. This keeps
the longer, more structured comment from moving the score: in controlled runs on interview 6837
(gpt-4.1, three repetitions), putting that comment structure and rewritten examples inside the scoring
prompt lowered the clarity score from a text-only median of 4.0 to 2.5, while the evidence alone left it
at 4.0. The comment is 3 to 5 sentences, ordered positive first and improvement last, and never returns to
a positive point after an improvement. It includes ONE broad sentence on the predominant paraverbal or
nonverbal pattern across the whole interaction: when favorable it follows the verbal strength, when
unfavorable it goes with the improvement, and when mixed it is split between both parts.

- The pattern sentence is controlled only by the prompt, with no validation in code.
- It uses plain qualifiers ("mostly", "at times", "rarely") and no numbers or units.
- It is framed as observable behavior that accompanies or nuances the verbal assessment ("is consistent with"). The prompt forbids verbs that credit the behavior with an effect, words for internal states ("warmth", "attention") and presenting the absence of nods or smiles as a shortfall. The signals remain complementary evidence and not measures of interest, empathy or clarity.
- Details about one specific moment stay out of this sentence: they belong to the learning moments (`learning-moments.md`).

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

`/recording/reprocess` regenerates observations and then reevaluates both
automatic conditions. `/evaluation/regenerate` reevaluates both conditions using
the saved observations. Each operation regenerates and stages a new TEXT_ONLY
run, then builds TEXT_PLUS_MULTIMODAL from that refreshed control and available
interest/empathy/clarity evidence, copying the other categories (and categories
without valid evidence) from the control. Both current evaluation rows update in
one transaction; append-only run snapshots preserve prior automatic results.
Superuser-only access within the same organization and mutual exclusion of
refresh operations remain. Completion still evaluates TEXT_ONLY once, waits for
observations, then assembles the full multimodal condition.

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

Tests cover the inherited text prompt plus one evidence block, full canonical transcripts with
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

- `app/agents/prompts/multimodal_evaluation.py`: registry, text prompt plus evidence block, comment prompt and localized evidence metadata.
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
