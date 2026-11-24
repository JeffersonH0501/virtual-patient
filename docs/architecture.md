# Architecture and operations

## Services

The [React/Vite UI](../virtual-patient-ui/src) owns routing, capture, the interview session and review. The [FastAPI entry point](../virtual-patient-api/main.py) serves interview, speech, review and administration requests. PostgreSQL and Alembic manage clinical cases, users, conversations, recordings, job state and assessments. The local and full Compose projects both separate the API from the media-processing worker. The setup service handles initialization and local development tooling.

The API authorizes users, persists lifecycle changes and queues work. The worker executes media jobs through the internal API-to-worker boundary. Native analysis is isolated from the request process. Capture and requests remain interactive while the durable queue handles replay generation and feature extraction. Use the resource limits in the active Compose file and measure representative interviews before drawing conclusions about capacity.

## Configuration and speech

Use the `.env.local.example` and `.env.full.example` inventories with their corresponding Docker workflows. Keep credentials in ignored runtime configuration. The [API configuration guide](../virtual-patient-api/config/README.md) describes the runtime prompt files, rules and seed data. The [deployment guide](../DEPLOYMENT.md) covers the commands, volumes, database preparation and full environment.

The browser sends authenticated speech input to the API for Azure OpenAI transcription. Written input remains available when audio fails. Patient TTS uses a structured delivery policy separate from the conversational prompt. Saved speech can be reused when its policy version is current. The exact delivered audio is available to [interview replay](interview-media.md#replay-and-analysis).

The [API orchestrator](../virtual-patient-api/app/multimodal/pipeline.py) coordinates extraction and lifecycle changes. [Turn result assembly](../virtual-patient-api/app/multimodal/turn_results.py) owns shared references, labels and persisted layers for processing and explicit maintenance. Keep extraction, descriptive labeling and [assessment](assessment-and-access.md) separate.

## Deployment scripts and tools

The [deployment scripts](../virtual-patient-api/scripts/deployment) prepare the database schema, administrator, LangGraph tables and initial clinical cases and personalities. The Bash deploy commands also use the deployment verifier to check the resulting database, native audio extraction and media worker.

The [manual tools](../virtual-patient-api/scripts/tools) cover latency benchmarks, Azure connectivity, interview inspection, Graphify and multimodal maintenance. Some tools make billable provider calls or write existing interview data. Run the relevant tool explicitly inside the existing Docker service. The [repository-level scripts](../scripts) include the deployment contract test and host wrappers for diagnostics.

## Observability

[Performance events](../virtual-patient-api/app/utils/perf.py) record operation, outcome, monotonic duration and technical metadata. The browser and API correlate requests through `X-Trace-Id`. Durable work also correlates by interview, recording or turn ID. Eligible interview events persist in `interview_performance_events` and are visible to administrators in the interview review. Calibration-test sessions are excluded from persistence. Interview deletion removes the associated timeline. Keep tokens, prompts, transcripts, clinical answers and media out of the events.

```bash
docker compose -f docker-compose.local.yml logs --since 15m api media-processing-worker | grep performance_event
```
