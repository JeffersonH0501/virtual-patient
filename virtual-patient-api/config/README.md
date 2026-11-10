# Backend functional configuration

These UTF-8 files are the source for new evaluations, patient conversations and
initial catalog data. The API reads them from this directory in both Docker
modes. Keep provider credentials and infrastructure settings in the deployment
environment. Restart the API and visual worker together after a development
configuration edit. Rebuild the production backend image to deploy a change.

| Directory | Content |
| --- | --- |
| `thresholds/` | Versioned base thresholds and session reference settings |
| `labels/` | Ordered integrated-label rules and descriptions of observed behavior |
| `prompts/` | Literal prompt templates, scoring instructions and multimodal evidence descriptions |
| `rubrics/` | The English and Spanish criteria in their established order, plus the human rating rubric version |
| `scoring/` | Completeness weights for progress and hypothesis results |
| `personalities/` | Patient portrayal profiles and the initial personality catalog |
| `clinical_cases/` | The full English and Spanish source records for all five bundled cases |

Preserve literal whitespace and placeholder names in prompt templates. Keep
rubric criteria aligned across both languages. Changes to scientific content
require a version and a record of the evaluation conditions before generating
new results. Existing run snapshots and teacher submissions retain their original
content and provenance. Extraction logic and quality checks remain in the
processing modules.

Database setup loads the case and personality sources when the corresponding
catalog is empty. Edits to these sources apply on an empty catalog. Existing
clinical and personality rows, historical cases and interview links retain
their values and IDs.
Each clinical case filename is its stable case key. Each file contains complete
`en` and `es` records, including their display fields and clinical histories.
The consolidation archive retains the historical migration inputs.

## Deployment settings

The local API and visual worker read deployment.json for media retention
and worker timeout. In the full deployment, Compose mounts the
operator's policy file over that path. The shared worker token comes from a
separate Compose secret in production. Native runtime limits are supplied to
the containers from native-runtime.conf. See DEPLOYMENT.md at the repository
root for provisioning and permissions.
