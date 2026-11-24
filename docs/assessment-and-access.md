# Assessment and access

## Two automatic conditions

`TEXT_ONLY` preserves the inherited evaluation. `TEXT_PLUS_MULTIMODAL` uses the same canonical conversation, six categories and 24 inherited criteria. The multimodal registry adds complementary evidence for interest, empathy and clarity. General communication, completeness and open communication reuse the stored textual results. A registered category without valid evidence also reuses its textual result. The recorded availability and policy version distinguish the fallback.

| Category | Context used by the current implementation |
| --- | --- |
| Interest | Visual orientation, head feedback and smile behavior while the patient speaks |
| Empathy | Valid speaking and listening evidence read with the conversational context |
| Clarity | Temporal and prosodic evidence on student speech |

The [evaluation service](../virtual-patient-api/app/multimodal/evaluation_service.py) associates observations by message identity. Text without matched media remains in the conversation. Prompts receive valid descriptive labels and selected verified durations or counts. Raw series and thresholds remain in processing data. The scoring call uses the inherited prompt plus the evidence block. A separate category comment uses the assigned score. Run provenance and availability identify the inputs and policy for review. A processing failure preserves the prior valid result where available.

## Learning moments

[Learning moments](../virtual-patient-api/app/multimodal/learning_moments.py) provide examples tied to interview turns. Generation and freshness are tracked independently from scores. Regeneration uses current source data and stale results remain distinguishable. Access follows the interview review rules. Replay links depend on an available turn window.

## Review visibility

[Review access](../virtual-patient-api/app/core/review_access.py) centralizes interview visibility and case disclosure. Owners submit their private six-category self-assessment before seeing automatic results for their finished interview. Assigned teachers must submit their own rating before seeing automatic results for that assignment. Drafts stay private. The API controls access to scores, learning moments and assessment metadata. Administrators can inspect both automatic conditions and submitted manual assessments within their authorized scope. The operational rating uses all six scores on the 0–5 scale and is separate from the study's expert reference.

The authenticated clinical-case catalog exposes simplified case content to ordinary users. The interview-scoped case endpoint authorizes owners, assigned teachers and administrators for review during processing or after completion. Source-case access and automatic feedback visibility are separate decisions. Personal and assigned interviews share history, with scoped ratings and pagination.

## Administration and media

The application uses `student`, `doctor` and `admin` internally. [User administration](../virtual-patient-api/app/routers/users.py) restricts managed accounts to the administrator's organization. Student registration requires a university and semester range. Administrators manage teacher assignments. Technical turn details and manual regeneration are administrator operations. Originals, calibration captures and previews are private and require server-side authorization.

Administrative deletion blocks active processing and stages media on the same volume before the database change. Recovery can restore or purge the staged media according to whether the corresponding database records still exist.

The automatic evaluation and product rating workflows are implemented application features. Independent expert agreement and study validity require research evidence.
