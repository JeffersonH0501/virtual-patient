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
volume. These settings are no longer environment variables; they are hardcoded
in the API:

- Storage root and minimum free-space guard: `MEDIA_STORAGE_ROOT` (`/app/media`)
  and `MEDIA_MIN_FREE_BYTES` (256 MiB) in `app/media/storage.py`.
- Retention, consent policy version, and duration tolerance:
  `MEDIA_RETENTION_DAYS` (`None`), `MEDIA_CONSENT_POLICY_VERSION`
  (`institutional-v1`), and `MEDIA_DURATION_TOLERANCE_MS` (500) in
  `app/routers/interview_recordings.py`.

`/app/media` is the in-container mount point backed by the `interview_media`
Docker volume; to change where media lands on the host, adjust that volume in
the compose file rather than the code. Retention has no expiry by default and
this release does not delete expired files automatically. Nginx streams uploads
without request buffering and does not expose the media directory as public
static content.
Playback is authorized by the API and supports HTTP Range requests.

Post-interview observations run through the staged multimodal pipeline, which
uses OpenSMILE for student audio and Py-Feat 2.1.1 for student video. The
pipeline is scheduled as a background task when a recording is finalized. Its
methodology (derivation parameters, threshold bands, and label rules) lives in
versioned YAML under `app/multimodal/config/`. Extractor runtime constants live
beside their implementations: OpenSMILE uses eGeMAPSv02 LLDs over mono 16 kHz
PCM, while Py-Feat uses Detectorv2 at 3 FPS with batches of 8 and stores
downloaded resources in the persistent `/app/pyfeat` volume. The API image uses
the official PyTorch CUDA 12.6 runtime and both Compose modes expose the NVIDIA
GPU to the API. Py-Feat selects CUDA automatically, reduces its batch through
`8, 4, 2, 1` if the device rejects the initial batch, and finally retries on CPU.
Pascal GPU use native CUDA convolution kernels; newer GPU retain cuDNN. A GPU
deployment therefore requires an NVIDIA driver and Docker GPU support, but no
host-side Python or CUDA toolkit installation.

Methodology values such as the gaze alignment tolerance and AU12 active
threshold are configured in `app/multimodal/config/processing.yaml`, not in
`.env`. They remain `null` (undecided) until the research procedure defines
them, and their dependent features are reported as unavailable rather than
guessed. See `app/multimodal/README.md` for the pipeline flow and the personal-
baseline calibration endpoint (`POST
/medical-interviews/calibration/baseline`). This endpoint processes temporary
media before an interview exists; the interview and its numeric baseline are
persisted only when the user confirms that the simulation should start.

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

This mode builds images without source mounts, keeps PostgreSQL on an internal
network, and publishes the UI through Nginx over HTTP and HTTPS. The UI reaches
the API through the `/api/` proxy; the API is not exposed directly to the host.

1. Create the configuration and replace every `change-me` value:

   ```bash
   cp .env.full.example .env.full
   ```

2. Install and validate certificates from the repository root:

   ```bash
   bash setup-tls.sh path/to/certificate.pem path/to/private-key.key
   ```

3. Build the services, prepare the database, and verify the deployment:

   ```bash
   bash deploy-full.sh setup
   ```

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

- creates the current SQLAlchemy schema in an empty database and stamps the
  active Alembic revision;
- applies `alembic upgrade head` to an existing versioned database;
- creates or migrates the LangGraph store and checkpoint tables idempotently;
- preserves all data and seeds only empty reference tables;
- stops when it finds existing tables without Alembic history instead of
  guessing a version or overwriting them.

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


### Email identity migration

The API now accepts `email` and `password` at `POST /auth/token`. Registration
requires `first_name` and `last_name`. Apply migration `021_email_identity`
before serving the new API/UI together (the normal setup flow upgrades to head).
Existing sessions must sign in again because JWT subjects now use account IDs.

Existing account IDs, password hashes, and relationships are preserved. Legacy
names are retained intact in `first_name` with an empty `last_name` pending an
explicit profile correction; compound names are not guessed. Invalid or duplicate
case-insensitive emails stop the migration before schema changes. Retired values
are stored only in `user_identity_migration_archive` for downgrade and are not
exposed by the API. That archive contains personal data and follows the same
access and retention controls as the user table.

The superuser now uses a single `SUPERUSER_NAME` value instead of separate
first/last name settings, matching the single `name` column on the user table.
Deployment environment files must provide `SUPERUSER_EMAIL`, `SUPERUSER_NAME`,
and `SUPERUSER_PASSWORD`. An existing
superuser whose email differs from the configured one is not renamed
automatically: resolve email collisions or duplicate superusers manually.

### Py-Feat observation migration

Migration `022_pyfeat_primary` promotes existing Py-Feat results to the
canonical `nonverbal_features` field and removes the former secondary field.
Rows that contain only results from the retired visual extractor become null so
that unavailable evidence is never presented as a Py-Feat result. Its downgrade
restores the former schema shape, but cannot reconstruct discarded observations.
