# Centralized deployment

Both execution modes are managed from this directory with Bash scripts. There
is no need to enter the API or UI directories or run PowerShell scripts. Docker
Desktop and Git Bash or WSL are required on Windows.

The only configuration inventories are `.env.local.example` and
`.env.full.example`. Docker Compose passes their values to the API and UI, so
the application directories do not maintain separate `.env.example` files.

## Reproducible local environment

The local environment binds only to `127.0.0.1`, mounts source code for hot
reload, and stores PostgreSQL data in a Docker volume.

```bash
cd virtual-patient
cp .env.local.example .env.local
bash deploy-local.sh setup
```

The UI is available at `http://127.0.0.1:5173`, and the API documentation is at
`http://127.0.0.1:8000/docs`. Azure credentials are optional when starting and
testing application flows that do not invoke AI. Real conversations,
evaluation, embeddings, and TTS require valid Azure configuration.

The integration derives `/openai/v1/` from `AZURE_OPENAI_ENDPOINT` for chat,
embeddings, and TTS. STT uses Azure's deployment-based audio endpoint with the
explicit `AZURE_OPENAI_API_VERSION`. In addition to the key and endpoint, it
defines five deployments: normal LLM, mini LLM, STT, TTS, and embeddings.
Production requires all five. The local environment
uses placeholders so services that do not invoke AI can still start. The
application initially uses the mini LLM, while both chat deployments remain
configured for explicit selection and validation.

The backend uses Azure OpenAI directly for TTS and STT. The browser input mode
remains a UI choice:

```bash
VITE_SPEECH_INPUT_PROVIDER=server
```

The active input mode records provisional utterance segments in the browser and
uploads each segment to the authenticated speech endpoint. The API
forwards the in-memory payload to Azure OpenAI. Browser speech recognition
remains an optional fallback and may use an external browser-vendor service.
Client-side audio activity only delimits STT requests; its boundaries remain
provisional interaction timing rather than validated VAD or evaluation evidence.
Patient TTS is streamed through the authenticated message speech endpoint and
is not uploaded to an external object-storage service.

Patient TTS uses a versioned vocal-style profile. Azure OpenAI maps the profile
to `gpt-4o-mini-tts` `instructions`. The profile affects
delivery only and must not add or rewrite transcript words. Stored audio paths
are not created; message metadata retains the policy version for reproducibility.

Interview recording uses a private filesystem provider and a persistent Docker
volume. Storage constants and operational policy are configured separately:

- Storage root and minimum free-space guard: `MEDIA_STORAGE_ROOT` (`/app/media`)
  and `MEDIA_MIN_FREE_BYTES` (256 MiB) in `app/media/storage.py`.
- Media retention is read from the deployment configuration file described below.
  Consent records are managed outside the application.
- Duration tolerance: `MEDIA_DURATION_TOLERANCE_MS` (500) in
  `app/routers/interview_recordings.py`; this deployment change does not alter it.

`/app/media` is the in-container mount point backed by the `interview_media`
Docker volume; to change where media lands on the host, adjust that volume in
the compose file rather than the code. New recordings retain their calculated
expiry date; deployment verification does not run media deletion. Nginx streams uploads
without request buffering and does not expose the media directory as public
static content.
Playback is authorized by the API and supports HTTP Range requests.

Post-interview observations run through the staged multimodal pipeline, which
uses OpenSMILE for student audio and a shared server-side video path for student
video: MediaPipe Face Landmarker, calibrated MediaPipe gaze and CCDb-HG
head-gesture inference, plus the smile blendshape logic. The pipeline is
scheduled as a background task when a recording is finalized. Its methodology
(threshold bands and label rules) lives in versioned YAML under
[`virtual-patient-api/config/`](virtual-patient-api/config/README.md). Extractor and derivation constants live beside
their implementations: OpenSMILE uses eGeMAPSv02 LLDs over mono 16 kHz PCM, and
the visual extractors ship their model assets in-repo (under
`app/nonverbal/models/`) or via pip. All video inference is CPU-only: the API
image installs the CPU PyTorch build, and neither Compose mode requires or
exposes an NVIDIA GPU, so no host-side Python or CUDA toolkit installation is
needed.

The gaze alignment tolerance and smile activation threshold live in the
visual extraction and preprocessing code. The threshold engine reports
dependent features as unavailable when a methodology value is explicitly `null`.
See `virtual-patient-api/app/multimodal/README.md` for the pipeline flow.
Calibration uses `POST /calibration/process-stage` after creating an owned,
unstarted interview draft. Migration `003_calibration_captures` adds private
reference videos and analysis outcomes, including failed attempts. Accepted signed
checkpoint IDs link those captures to the interview profile. The review header's
Calibration dialog is restricted to superusers with interview/organization access.
The existing expiry job purges started-interview calibration media within twelve
calendar months from capture. Preparation media is temporary: confirmed exit
discards only calibration media/results, preserving the interview record. A
five-minute sweep clears abandoned calibration after one inactive hour
and unreferenced calibration files after five minutes. The browser cannot set
`calibration_activity_at` or `calibration_discarded`. Cleanup shares interview row locks with upload/start; interview deletion removes both rows
and files. Worker input copies remain temporary.

During an interview, four continuous sources share one browser clock:
`student_audio`, `student_video`, `patient_audio`, and `patient_video`. Student
video is a 1280x720 canvas representation of the camera feed, while patient
video is a rendered virtual-patient panel rather than a physical camera signal.
Patient audio is generated TTS, and student audio is captured from the
microphone independently of browser speech recognition. OPFS is used for
temporary chunks when supported, with an in-memory fallback. The transcript
remains usable when capture or upload fails.

Common commands:

```bash
bash deploy-local.sh status
bash deploy-local.sh logs api
bash deploy-local.sh verify
bash deploy-local.sh restart
bash deploy-local.sh down
```

The Azure connectivity check makes billable requests and is not part of
`verify` or the automated test suite. Run it only deliberately:

```bash
docker compose --env-file .env.local -f docker-compose.local.yml exec api \
  python scripts/check_azure.py
```

The script reports normal chat, mini chat, embeddings, TTS, and STT separately.
It passes the TTS audio to STT in memory. If TTS fails, it reports STT as
blocked. This check does not change the UI provider selected at build time.

`down` preserves the database. To prepare the schema again without restarting
the UI and API:

```bash
bash deploy-local.sh database
```

## Full deployment

Both startup scripts include the internal `video-processing-worker` in setup,
up, and restart. `verify` checks database metadata, real OpenSMILE extraction
and voice calibration on generated audio, and the worker health endpoint. It
does not access participant media or call Azure. Native audio failure stops
verification even when `pip check` succeeds.

The existing API image uses `requirements.constraints.txt` to preserve the
qualified dependency versions. PyArrow 20.0.0 supports the retained NumPy
1.26.4 runtime; PyArrow 26 requires NumPy 2. Rebuild the existing API/worker
images after dependency changes. Do not install packages in running containers.
Changing these constraints requires compatibility and extraction checks rather
than an unrestricted upgrade.

Preserve the existing fresh-process pipeline and separate visual worker. The
supported pipeline extracts audio before loading visual models. Native integration
tests use the same fresh-process boundary and fail on a nonzero process exit.

With the local API running, validate orchestration and the actual full Compose
contract using synthetic settings without starting production:

```bash
bash scripts/tests/test_deployment.sh
```

This mode builds images without source mounts, keeps PostgreSQL on an internal
network, and publishes the UI over HTTP on `127.0.0.1:${HTTP_PORT:-8091}`.
The host Nginx terminates public HTTPS and proxies to that loopback address.
The container serves the UI and forwards `/api/` to the internal API.

1. Create the configuration and replace every `change-me` value:

   ```bash
   cp .env.full.example .env.full
   ```

   Set `VITE_RECAPTCHA_SITE_KEY` and `RECAPTCHA_SECRET_KEY` to a matching
   reCAPTCHA v2 pair authorized for the deployment domain. The API verifies
   the token on both login and registration. The production proxy also limits
   authentication and transcription by source IP and returns HTTP 429 on excess.

2. Prepare the deployment policy and private worker token from the repository root.

   ```bash
   mkdir -p config
   cp virtual-patient-api/config/deployment.json config/deployment.json
   mkdir -m 700 -p config/secrets
   chmod 700 config/secrets
   (umask 077; openssl rand -hex 32 > config/secrets/video-processing-worker-token.txt)
   chmod 0444 config/secrets/video-processing-worker-token.txt
   ```

   Keep the token directory private. The token file must be readable by the
   non-root container process through its read-only Compose secret mount.
   Generate it only on initial setup or planned rotation. Recreate the API
   and visual worker together after changes to the token or runtime files.
   Tune native thread limits in virtual-patient-api/config/native-runtime.conf.

3. Build the services, prepare the database, and verify the deployment:

   ```bash
   bash deploy-full.sh setup
   ```

4. Configure the host Nginx virtual host with a valid public certificate.
   Proxy to `http://127.0.0.1:8091` (or the configured `HTTP_PORT`) and
   preserve the original `Host` and HTTPS scheme. Set the host proxy body
   limit to accommodate recording uploads (up to 1156 MiB).

Operational commands:

```bash
bash deploy-full.sh status
bash deploy-full.sh logs
bash deploy-full.sh verify
bash deploy-full.sh restart
bash deploy-full.sh down
```

A production server also needs DNS, valid certificates, firewall rules,
PostgreSQL volume backups, and an external secret-management strategy. Docker
Compose does not replace those infrastructure controls.

## Database preparation

Both modes call `virtual-patient-api/scripts/setup_db.py`. The process:

- applies `alembic upgrade head` to create the application schema in an empty
  database or upgrade a database already on the release migration history;
- adopts the release baseline for a database at `033_teacher_grading` after
  comparing its application schema with the frozen baseline. Setup adds the
  durable jobs table and snapshot trigger if the previous bootstrap omitted them;
- creates or migrates the LangGraph store and checkpoint tables idempotently;
- preserves all data and seeds only empty reference tables;
- stops on an unversioned, older, or incompatible schema.

Database setup also provisions exactly one `superuser` from `SUPERUSER_EMAIL`,
`SUPERUSER_NAME`, and `SUPERUSER_PASSWORD` (the account uses a single display
name). Setup rejects missing values. Re-running setup synchronizes that sole
account with the configured identity and password; if multiple superusers or a
email collision exists, setup stops for manual resolution. Public
registration only accepts `student` and `teacher`, and self-service profile
updates cannot change roles or organization membership.

The API repeats the same idempotent synchronization on every process startup,
so changes to the configured superuser identity, password, or preferred
language take effect after restarting the API. The preferred language defaults
to Spanish (`es`). Use `bash deploy-local.sh restart` or
`bash deploy-full.sh restart` after changing the environment file; these
commands recreate the application containers because a plain Docker restart
does not reload environment variables.

The PostgreSQL container creates the database named by `POSTGRES_DB`.
`setup_db.py` prepares its schema and does not manage server-level databases.


### Adopt the release baseline on an existing database

Take a backup and stop application traffic before running the normal setup
command against an existing database. Use setup for the transition from
`033_teacher_grading` so it can verify the schema before updating the revision.
Setup accepts the equivalent index and constraint definitions and the known
server defaults left by earlier incremental migrations. These definitions,
application rows, and separately managed LangGraph data stay in place.

For an older revision, use the previous deployment that contains the legacy
migration chain to reach `033_teacher_grading` before updating the application.
If the schema fails validation, reconcile it on a verified copy of the backup
before retrying. Restore the backup and previous deployment if a rollback is
required.


The feature-family terminology revision updates only current observation labels
and the evidence identifiers in learning moments. Run database setup before
serving the updated application. Scores, recordings and immutable evaluation
snapshots retain their original values. Saved learning moments can become stale
because the evidence identifiers are part of the freshness check.
