# Virtual Patient

Virtual patient application for clinical history-taking training. The repository contains a FastAPI/PostgreSQL API and a React/Vite user interface.

## Project Background

This repository extends the earlier Virtual Patient implementation developed by Andrea Bayona. The current work builds on that foundation as part of a master's thesis focused on expanding the platform toward multimodal clinical-interview training and evaluation.

The original authorship and license notices included in the inherited source code are preserved. New work in this repository includes the current deployment structure and the ongoing multimodal extensions, including interview recording, synchronized recap, paraverbal analysis with OpenSMILE/eGeMAPSv02, non-verbal feature extraction with OpenFace 3.0, and related research-oriented processing infrastructure.

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

The interview screen is presented as a call and captures four private, continuous sources on one browser timeline: student microphone audio, student camera canvas, patient TTS audio, and the rendered patient canvas. Turning off the microphone or camera preserves silence or a disabled-camera frame instead of shortening the timeline. Temporary chunks use OPFS when available and fall back to memory; completed files are uploaded to authenticated private storage.

After an interview, the recap view synchronizes the two recorded video panels and mixes the two audio sources locally. Seeking also updates the cumulative transcript. Legacy interviews and failed captures retain their full transcript and explicitly report that no recording is available. At finalization, the API can derive descriptive, per-student-turn OpenSMILE/eGeMAPSv02 observations from the private student-audio recording and OpenFace 3.0 observations from the private student-video recording. Video outputs include face-tracking validity; gaze and AU12 aggregates require explicit research configuration. The pause, gaze and AU rules are provisional processing parameters; this does not validate VAD, visual alignment, nod detection, non-verbal inference, or multimodal evaluation.

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
