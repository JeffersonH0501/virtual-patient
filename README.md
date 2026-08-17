# Virtual Patient

Virtual patient application for clinical history-taking training. The
repository contains a FastAPI/PostgreSQL API and a React/Vite user interface.

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

Each application has a single `Dockerfile`. Configuration is defined only
through `.env.local` or `.env.full` in this directory. Their corresponding
`.example` files are the configuration inventories.

Azure OpenAI uses the standard SDK against the v1 API. The application appends
`/openai/v1/` to `AZURE_OPENAI_ENDPOINT`. The configured normal LLM, mini LLM,
STT, TTS, and embedding values are deployment names from the same Azure
resource.

## Quick start

Docker Desktop and Bash are required. On Windows, use Git Bash or WSL.

```bash
cp .env.local.example .env.local
bash deploy-local.sh setup
```

- UI: `http://127.0.0.1:5173`
- API: `http://127.0.0.1:8000/docs`

See [DEPLOYMENT.md](DEPLOYMENT.md) for local operation, full deployment, TLS,
and database preparation.
