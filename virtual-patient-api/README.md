# Virtual Patient API

A comprehensive backend API for medical education simulations featuring interactive patient interviews, real-time messaging, hypothesis tracking, and progress monitoring. Built with FastAPI, PostgreSQL, and WebSocket support for real-time communication.

## Features

- **Interactive Medical Interviews**: Conduct real-time conversations with AI-powered virtual patients
- **Real-time Messaging**: WebSocket support for instant message exchange
- **Hypothesis Management**: Track and evaluate diagnostic hypotheses with confidence levels
- **Progress Monitoring**: Live progress summaries and session notes
- **Clinical Case Management**: Default and custom clinical cases with detailed patient profiles
- **User Authentication**: JWT-based authentication with role management
- **Organization Support**: Multi-tenant architecture for educational institutions
- **Comprehensive Analytics**: Track interview performance and learning outcomes

## System Architecture

- **API Layer**: FastAPI with automatic OpenAPI documentation
- **Database**: PostgreSQL with optimized schema and indexes
- **Real-time Communication**: WebSocket support for live interview sessions
- **Authentication**: JWT tokens with secure password hashing
- **AI Integration**: Ready for GPT agent integration for patient responses

## Requirements

- Python 3.9+
- PostgreSQL 12+
- Virtual environment (recommended)

## Quick Start

### 1. Environment Setup

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment Variables

Create a `.env` file in the project root:

```env
POSTGRES_USER=your_db_user
POSTGRES_PASSWORD=your_db_password
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=virtual_patient
SECRET_KEY=your_secret_key_here_change_in_production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Azure OpenAI Configuration (Required for AI features)
AZURE_OPENAI_API_KEY=your_azure_openai_api_key_here
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=your-deployment-name
AZURE_EMBEDDING_DEPLOYMENT=your-embedding-deployment-name
AZURE_OPENAI_API_VERSION=2024-02-15-preview

# Google Cloud Storage Configuration (Optional - for TTS audio storage)
GCS_BUCKET_NAME=your-gcs-bucket-name
GCS_CREDENTIALS_PATH=/path/to/gcs-credentials.json
```

**Note:** You'll need an Azure OpenAI resource with:

- A GPT-4 deployment for chat completions
- A text-embedding-ada-002 deployment for embeddings

### 3. Database Setup

#### Install pgvector Extension (Required for Semantic Search)

The system uses PostgreSQL with the pgvector extension for semantic search capabilities. Follow these steps to set it up:

**On macOS (using Homebrew):**

```bash
# Install pgvector
brew install pgvector

# Start PostgreSQL service (if not already running)
brew services start postgresql@14

# Enable the vector extension in your database
psql -U your_db_user -h localhost virtual_patient -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

**On Ubuntu/Debian:**

```bash
# Install pgvector
sudo apt-get install postgresql-14-pgvector

# Enable the vector extension in your database
sudo -u postgres psql -d virtual_patient -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

#### Create Database and Tables

```bash
# Create database and tables
python scripts/setup_db.py

# Seed with default clinical cases
python scripts/seed_clinical_cases.py
```

### 4. Run the Application

```bash
# Development mode with auto-reload
uvicorn main:app --reload --host 0.0.0.0 --port 8000

# Or using the main.py script
python main.py
```

The API will be available at `http://localhost:8000`

## API Documentation

- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

## Core Features

### Medical Interviews

- Create new interview sessions with specific clinical cases
- Real-time message exchange via WebSocket
- Track interview progress and duration
- Complete interviews with final assessments

### Messaging System

- Bidirectional communication between user and virtual patient
- Message history with timestamps
- Support for different message types (text, structured data)
- Real-time delivery via WebSocket

### Hypothesis Management

- Submit diagnostic hypotheses during interviews
- Confidence level scoring (1-10)
- Reasoning documentation
- Hypothesis tracking and evaluation

### Progress Monitoring

- Live progress summaries during interviews
- Key findings and pending questions
- Confidence scores for assessment completeness
- Session notes for documentation

## Database Schema

The system includes the following main tables:

- `users` - User accounts and authentication
- `organizations` - Educational institutions
- `clinical_cases` - Patient case definitions
- `medical_interviews` - Interview sessions
- `interview_messages` - Message history
- `user_hypotheses` - Diagnostic hypotheses
- `session_notes` - Interview documentation
- `progress_summaries` - Live progress tracking

## WebSocket Events

Real-time communication supports these events:

- `join_interview` - Join an active interview session
- `send_message` - Send a message to the virtual patient
- `receive_message` - Receive responses from the virtual patient
- `update_progress` - Live progress updates
- `submit_hypothesis` - Submit diagnostic hypotheses

## Authentication

All API endpoints require JWT authentication:

```bash
# Login to get token
curl -X POST "http://localhost:8000/token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=your_username&password=your_password"

# Use token in requests
curl -H "Authorization: Bearer <your_token>" \
  "http://localhost:8000/api/v1/interviews"
```

## Development

### Database Management

```bash
# Connect to database
psql -h localhost -p 5432 -U your_db_user -d virtual_patient

# View tables
\dt

# View table structure
\d medical_interviews
\d interview_messages
```

### Running Database Migrations (Alembic)

When working with a local database (without Docker), you can run Alembic migrations directly:

```bash
# Apply all pending migrations
python -c "from alembic.config import Config; from alembic import command; import sys; sys.path.insert(0, '.'); alembic_cfg = Config('alembic.ini'); command.upgrade(alembic_cfg, 'head'); print('✅ Migration applied successfully!')"

# View migration history
python -c "from alembic.config import Config; from alembic import command; alembic_cfg = Config('alembic.ini'); command.history(alembic_cfg)"

# Check current database revision
python -c "from alembic.config import Config; from alembic import command; alembic_cfg = Config('alembic.ini'); command.current(alembic_cfg)"
```

**Note**: Make sure you have all required dependencies installed (`alembic`, `sqlalchemy`, `psycopg2-binary`, `pydantic`, `python-dotenv`, `email-validator`) and that your `.env` file contains the correct database connection details.

### Adding New Clinical Cases

Edit files in `scripts/default_cases/` and re-run:

```bash
python scripts/seed_clinical_cases.py
```

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
pytest
```

## Production Deployment

- Use environment variables for all sensitive configuration
- Set up proper PostgreSQL connection pooling
- Configure WebSocket proxy (nginx) for production
- Implement proper logging and monitoring
- Set up SSL/TLS certificates
- Configure CORS for your frontend domain

## API Endpoints

See [API_ENDPOINTS.md](./API_ENDPOINTS.md) for complete endpoint documentation with examples.

## System Documentation

See [MEDICAL_INTERVIEW_SYSTEM.md](./MEDICAL_INTERVIEW_SYSTEM.md) for detailed system architecture and design decisions.

## License

MIT

# Cursor run command

cd /Users/andrea.bayona/Documents/GitHub/virtual-patient-api && .venv/bin/python test_multilingual_clinical_cases.py
