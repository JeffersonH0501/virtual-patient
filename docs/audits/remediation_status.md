# Audit remediation status — 13 October 2026

The user requested a closeout to prioritize other urgent changes. The original experiment readiness audit remains historical evidence and is not a claim that every finding has been resolved.

Implemented:

- Public registration accepts students only, including direct API requests. The role selector is removed and password confirmation is required in the UI. Password recovery view, route, links and translations are removed.
- Superusers have a Users navigation tab and can create/list student and teacher accounts within their organization. Administrative creation returns user data, never login tokens or password hashes. Other roles cannot use these endpoints.
- Organization-scoped interview access and owner-only mutations; capture and conversation writes are rejected after capture closes. Message ordering uses timestamp and ID. Student/patient message pairs commit together.
- Event timestamps survive queued persistence and later pauses. Turn recorders pause with continuous capture. Encoded media duration is inspected with FFprobe.
- Unavailable gaze observations and timestamp gaps break dwell episodes. Nod inference requires local evaluated timestamps; interpolation and event consolidation reject gaps. Visual evidence has family-specific operational coverage gates. Invalid/clipped/truncated audio is unavailable.
- Held-out gaze calibration checks and server-signed checkpoints; session geometry changes invalidate calibrated gaze. The patient ROI follows the avatar. Final processing and regeneration use full-session video.
- Immutable evaluation snapshots, provider metadata allowlists, stale-evaluation indication, and PostgreSQL-backed completion/extraction/evaluation jobs. Migrations 030 and 031 were applied locally. Technical evaluation failures no longer fabricate a score of 2.5; successful inherited rubric logic is preserved.
- An optional superuser research endpoint creates a matched text control using enriched prompts/schema with unavailable evidence. It is not run automatically and does not replace either application condition.
- Sensitive agent/controller debug prints removed. HTTP-only replay cookies, expiry, and production configuration guards added.
- Maximum media retention is **12 calendar months**, as explicitly authorized by the user. Shorter configured periods are allowed. Expiry processing covers historical rows without deadlines. Research records, graph memory and backups have separate unresolved erasure requirements.
- Web dependencies updated in the existing Docker image: FastAPI 0.121.3, Starlette 0.50.0, python-jose 3.5.0, python-multipart 0.0.22, requests 2.32.5. API and video worker were recreated with that image.

Validation completed inside the existing Docker environment: targeted API/visual/retention/authentication/evaluation tests passed; the updated readiness script passed (event clock, 19 API tests, 21 visual tests); UI tests passed (20); full UI lint passed, later affected-file lint passed, UI build passed, later TypeScript checks passed; pip check passed. Compilation passed using a temporary container bytecode cache because the Windows-mounted cache directories denied writes. No paid evaluation, live camera/microphone trial or expert validation was performed.

Still open: confirmed consent version and Azure transfer authorization; expert assignment policy; empirical signal/synchronization/feedback qualification; graph/checkpoint/shared-memory and backup erasure; hardware/load/restart qualification beyond unit tests; speech/pause proxy validity and request idempotency; comprehensive dependency remediation. The post-update scan still reports 20 affected Python distributions and 113 Yarn advisory entries, including development tools. Updating these five web packages did **not** eliminate every advisory. The optional matched control has mock-level validation; it has not been experimentally compared.

The application changes above are available for development. Recruitment readiness is not established. The sibling thesis manuscript was not edited during this remediation.
