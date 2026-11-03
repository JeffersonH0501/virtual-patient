# Virtual Patient

Virtual patient application for clinical history-taking training. The repository contains a FastAPI/PostgreSQL API and a React/Vite user interface.

## Project Background

This repository extends the earlier Virtual Patient implementation developed by Andrea Bayona. The current work builds on that foundation as part of a master's thesis focused on expanding the platform toward multimodal clinical-interview training and evaluation.

The original authorship and license notices included in the inherited source code are preserved. New work in this repository includes the current deployment structure and the ongoing multimodal extensions, including interview recording, synchronized recap, paraverbal analysis with OpenSMILE/eGeMAPSv02, non-verbal feature extraction with MediaPipe Face Landmarker, BlazeGaze/WebEyeTrack and CCDb-HG, and related research-oriented processing infrastructure.

## Structure

```text
virtual-patient/
├── virtual-patient-api/    # API, agents, models, and migrations
├── virtual-patient-ui/     # Web interface and Nginx proxy
├── deploy-local.sh         # Reproducible development environment
├── deploy-full.sh          # Full HTTPS deployment
├── setup-tls.sh            # Certificate installation and validation
├── docker-compose.local.yml
└── docker-compose.full.yml
```

Each application has a single `Dockerfile`. Configuration is defined only through `.env.local` or `.env.full` in this directory. Their corresponding `.example` files are the configuration inventories.

Azure OpenAI uses the standard SDK against the v1 API. The application appends
`/openai/v1/` to `AZURE_OPENAI_ENDPOINT` for chat, embeddings, and TTS. STT uses
Azure's versioned deployment endpoint. The configured normal LLM, mini LLM,
STT, TTS, and embedding values are deployment names from the same Azure
resource.

Speech behavior is selected independently from Azure credentials. The backend
uses Azure OpenAI for patient TTS and student STT. The active interview input is
`VITE_SPEECH_INPUT_PROVIDER=server`: the browser delimits provisional audio
segments and sends them to the authenticated API without persisting them as
part of the transcription request. `VITE_SPEECH_INPUT_PROVIDER=browser` remains
available as a fallback behind the same UI contract. Permission, device, codec,
and provider failures leave written input available.

Virtual-patient personality is split between semantic behavior and vocal delivery. Agent prompts determine what the patient says. A provider-neutral vocal-style policy determines pace, pause frequency, energy, intonation, hesitation, and configured delivery tone. The Azure OpenAI adapter translates that structured profile into `gpt-4o-mini-tts` `instructions` while requiring the supplied transcript to remain unchanged. The policy version and synthesis parameters are recorded in message metadata; durable audio is reused only when its policy version is current.

The speech profile also carries the interview response language through synthesis and avatar-session creation. The Tavus conversation is restricted to that language, and Azure TTS receives an explicit language direction. Optional gender-specific Tavus faces (`TAVUS_FACE_ID_MALE`/`TAVUS_FACE_ID_FEMALE`) or a `TAVUS_FACE_MAP` keyed by gender, age group and personality override the shared face; personality-specific vocal delivery is carried by the supplied audio and therefore informs Echo's synchronized animation.

The interview screen is presented as a call and captures four private, continuous sources on one browser timeline: student microphone audio, student camera canvas, patient TTS audio, and the rendered patient canvas. Turning off the microphone or camera preserves silence or a disabled-camera frame instead of shortening the timeline. Temporary chunks use OPFS when available and fall back to memory; completed files are uploaded to authenticated private storage.

After an interview, the recap view synchronizes the two recorded video panels and mixes the two audio sources locally. Seeking also updates the cumulative transcript. Legacy interviews and failed captures retain their full transcript and explicitly report that no recording is available. At finalization, the API derives descriptive OpenSMILE/eGeMAPSv02 observations for student speech and non-verbal observations from the private student video using the shared MediaPipe Face Landmarker, BlazeGaze/WebEyeTrack gaze and CCDb-HG head-gesture path. The turn-details dialog presents only the selected raw variables grouped by family. Gaze aggregates that require calibration remain unavailable until configured. These processing parameters do not validate VAD, visual alignment, nod detection, non-verbal inference, or multimodal evaluation.

## Optional Tavus avatar

When `TAVUS_API_KEY` and `TAVUS_PAL_ID` are set, the patient is rendered as a [Tavus](https://www.tavus.io) real-time avatar instead of the static image. If they are empty, Tavus is unreachable, or the browser cannot join the room, the interview silently keeps the static avatar with Azure TTS playback.

How it works:

1. The API (`POST /medical-interviews/{id}/avatar/session`) creates a private Tavus conversation (`require_auth`, bounded by `TAVUS_MAX_CALL_DURATION_SECONDS`) and returns only the room URL and a meeting token. The Tavus key never reaches the browser. The session is ended with `DELETE` on the same route, when the page is left, or by Tavus timeouts.
2. The `PAL` must use `pipeline_mode: "echo"`. This is not a setting in the Tavus dashboard: create the PAL through the [Echo Mode API quickstart](https://docs.tavus.io/sections/conversational-video-interface/echo-mode), then copy the returned `pal_id` into `TAVUS_PAL_ID`. For example:

   ```sh
   curl --request POST \
     --url https://tavusapi.com/v2/pals \
     --header 'Content-Type: application/json' \
     --header "x-api-key: ${TAVUS_API_KEY}" \
     --data '{"pal_name":"Virtual Patient Echo","pipeline_mode":"echo","default_face_id":"<face_id>"}'
   ```

   `default_face_id` is required; list the available faces with `GET https://tavusapi.com/v2/faces`. Set `TAVUS_API_KEY` in your shell before running the command; do not commit or share it. Tavus then skips its own STT, LLM and TTS: the existing LLM response and Azure TTS (including `vocal_style_policy`) are preserved.
3. The browser joins the room with `@daily-co/daily-js` without microphone or camera, converts the Azure MP3 to 16 kHz mono PCM16 and sends it as `conversation.echo` audio events. The remote video and audio feed the existing 4-track recording (`patient_video` and `patient_audio`) and the turn timings.

The LangGraph workflow resolves one patient speech profile after generating and translating each response. This is a profile-preparation/render-coordination stage, not a second conversation or video transport: the authorized speech endpoint still synthesizes audio on demand, while Tavus video travels over the private Daily room. See [Tavus integration and architecture](./docs/TAVUS_AVATAR.md) for the API/UI contract, state flow, configuration and latency instrumentation.

Operational notes:

- The Echo audio format (base64 PCM16 mono at the declared `sample_rate`), lip-sync quality, latency and `MediaRecorder` capture of the remote video must be validated with a real Tavus account before production use. The comparative evaluation (`Evaluacion_Avatar_VirtualPatient.pdf`) lists latency of roughly 600 ms, about USD 59/month for 100 minutes (USD 0.32-0.37/extra minute) and a free plan limited to proof-of-concept use; these figures come from the provider and must be confirmed.
- The UI exposes connection/playback/fallback states. Browser development tools show per-turn timings for message response, TTS, PCM conversion, Echo delivery and Tavus's first speaking event; the TTS endpoint includes `Server-Timing`. Audio delivery remains whole-clip until real-account measurements establish that incremental delivery is supported and beneficial.
- Credits are consumed while a conversation is open. A concurrency slot is held until it ends.
- Student and patient audio/video are processed by a third party. SOC 2/HIPAA coverage requires the Tavus Enterprise plan; obtain written data-handling terms and informed consent before using real participants. Tavus has no self-hosted option.

## Security and Configuration

Runtime secrets and credentials must not be committed to the repository. Local and deployment configuration should be created from the provided `.env.*.example` files and stored only in ignored `.env.local` or `.env.full` files. Administrative accounts must be provisioned separately; database migrations do not contain default administrator credentials.

## Quick start

Docker Desktop and Bash are required. On Windows, use Git Bash or WSL.

```bash
cp .env.local.example .env.local
bash deploy-local.sh setup
```

- UI: `http://127.0.0.1:5173`
- API: `http://127.0.0.1:8000/docs`

See [DEPLOYMENT.md](DEPLOYMENT.md) for local operation, full deployment, TLS, and database preparation.
