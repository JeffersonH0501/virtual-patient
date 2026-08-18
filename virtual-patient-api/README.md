# Virtual Patient API

FastAPI service for the virtual patient. It implements authentication,
organizations, clinical cases, interviews, messages, hypotheses, notes,
evaluation, and agents powered by Azure OpenAI and LangGraph.

## Organization

```text
app/
├── agents/       # Agent workflows, prompts, and schemas
├── controllers/  # Application logic
├── core/         # Configuration, authentication, and database
├── media/        # Private media-storage contract and filesystem provider
├── models/       # SQLAlchemy models and Pydantic schemas
├── routers/      # HTTP and WebSocket contracts
└── utils/        # TTS, GCS, and domain utilities
alembic/          # Database migrations
scripts/          # Initialization, validation, and reference data
```

## Configuration

Configuration is centralized at the repository root. Development uses
`.env.local`, copied from `.env.local.example`. Server deployments use
`.env.full`, copied from `.env.full.example`. `app/core/config.py` is the only
application entry point for environment configuration.

Do not create `.env` or `.env.example` files inside this directory.

`app/core/azure_openai.py` centralizes Azure OpenAI v1 clients. It constructs
the `base_url` from the resource endpoint and passes deployment names as
`model`. `ACTIVE_LLM_VARIANT` selects `LLMVariant.MINI` or
`LLMVariant.NORMAL` globally and is currently set to mini.

The embedding deployment converts textual memories into vectors for semantic
search. It must support 1536 dimensions. Changing the model or dimensions
invalidates the existing vector index and requires reindexing stored memories.

Each new interview accepts `patient_response_language` with `en` or `es` and
stores it as `interview_metadata.patient_response_language`. The virtual
patient and browser speech recognition use this interview setting independently
from the user's interface language. Legacy interviews without the setting keep
using the user's preferred language.

Completed interviews can persist four independent synchronized media assets:
student microphone audio, student camera-canvas video, patient TTS audio, and
rendered patient video. `MEDIA_STORAGE_ROOT` points to private storage outside
the web server's static resources. The recording API stores only opaque keys,
checks per-source durations, authorizes owner/teacher/superuser access, and
streams playback with HTTP Range support. `MEDIA_RETENTION_DAYS` records an
optional expiry timestamp but does not trigger deletion in this release.

When `PARAVERBAL_ANALYSIS_ENABLED=true`, finalizing a recording extracts an
OpenSMILE/eGeMAPSv02 summary from each timestamped student turn in the private
`student_audio` file. It persists only the structured observation in
`interview_turns.paraverbal`; patient turns remain `null`. FFmpeg is used only
to create temporary, clock-aligned WAV segments and those segments are deleted
after extraction. `PARAVERBAL_MIN_PAUSE_MS` and
`PARAVERBAL_MIN_VOICED_DURATION_MS` are provisional research parameters, not
clinical thresholds or performance labels.

When `NONVERBAL_ANALYSIS_ENABLED=true`, finalization samples private
`student_video` frames and runs the OpenFace 3.0 package once for the
interview. The per-turn result is stored in `interview_turns.nonverbal_features`
and reports video-validity quality. `OPENFACE_GAZE_ALIGNMENT_MAX_RADIANS`,
`OPENFACE_AU12_INDEX`, and `OPENFACE_AU12_ACTIVE_THRESHOLD` are deliberately
empty until calibrated; their dependent metrics remain unavailable rather than
being fabricated. The upstream OpenFace 3.0 output used here does not expose
head pose, so nod measures remain unavailable pending a separately validated
detector. Before enabling extraction, obtain the upstream weights with:

```bash
openface download --output /app/openface/weights
```

## Recommended execution

From the `virtual-patient/` repository root:

```bash
bash deploy-local.sh setup
```

The API is available at `http://127.0.0.1:8000`. OpenAPI documentation is
available at `/docs` and `/redoc`.

## Database

Deployments automatically run the non-destructive initializer:

```bash
python scripts/setup_db.py
```

It creates the current schema and stamps the Alembic revision in an empty
database. It applies pending migrations to a versioned database, creates or
migrates the LangGraph store and checkpoint tables idempotently, and seeds
clinical cases and personalities only when their tables are empty. It stops
when application tables exist without Alembic state.

Run the minimum deployment verification with:

```bash
python scripts/verify_deployment.py
```

Persistence changes require a reversible Alembic migration. `create_all` does
not replace migrations for an existing database.

## Validation

```bash
python -m compileall app main.py scripts
```

The external Azure check is separate from local tests because it makes billable
requests. Run it only with explicit authorization:

```bash
python scripts/check_azure.py
```

The check validates both chat deployments, a 1536-dimensional embedding
vector, TTS, and STT independently. It passes TTS audio to STT in memory and
does not persist it. Missing configuration or any component failure produces a
non-zero exit code.

Procedural memory requires Azure and is initialized explicitly with
`scripts/initialize_procedural_memory.py`. It is not part of local bootstrap
without credentials.
