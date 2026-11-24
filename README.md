# Virtual Patient

Virtual patient application for clinical history-taking training. The repository contains a FastAPI/PostgreSQL API and a React/Vite user interface.

## Project Background

This repository extends the earlier Virtual Patient implementation developed by Andrea Bayona. The current work builds on that foundation as part of a master's thesis focused on expanding the platform toward multimodal clinical-interview training and evaluation.

The original authorship and license notices included in the inherited source code are preserved. New work in this repository includes the current deployment structure and the ongoing multimodal extensions, including interview recording, synchronized recap, paraverbal analysis with OpenSMILE/eGeMAPSv02, non-verbal feature extraction with MediaPipe Face Landmarker and CCDb-HG, and related research-oriented processing infrastructure.

## Documentation

The [technical documentation](docs/README.md) covers architecture, interview media, evaluation, access and the web UI. The API and UI each use their existing Dockerfile. The local and full Compose configurations define the runtime services and volumes.

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
