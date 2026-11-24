from app.routers import doctor_grading
from app.routers import perception_survey
import logging

import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.admin_account import synchronize_admin
from app.speech.azure_openai import close_speech_clients
from app.routers import (
    auth, users, clinical_cases, 
    medical_interviews, medical_interview_session_notes, medical_interview_doctor_feedback, interview_messages, interview_hypotheses, summary, personalities, evaluations, speech, interview_recordings, recording_segments, calibration, interview_performance
)

# Uvicorn configures its own handlers, but application loggers otherwise keep
# the default WARNING threshold. Enable privacy-safe operational INFO events
# such as ``performance_event`` without increasing third-party logger noise.
logging.getLogger("app").setLevel(logging.INFO)

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Synchronize deployment-managed accounts whenever the API starts.

    The API never runs heavy background work. The durable processing-job loop
    (replay preview, multimodal pipeline, evaluation, learning moments) and the
    periodic media/calibration maintenance run in the media-processing-worker
    service. The API only stages jobs and serves their results.
    """
    with SessionLocal() as session:
        print(synchronize_admin(session))
    try:
        yield
    finally:
        close_speech_clients()
        from app.core.langgraph_runtime import close_langgraph_pool
        close_langgraph_pool()


app = FastAPI(
    lifespan=lifespan,
    openapi_url=None if settings.environment.lower() in {"production", "prod"} else "/openapi.json",
    title="Virtual Patient API",
    description="""
    A comprehensive medical education platform for conducting interactive patient interviews.
    
    ## Features
    
    * **Medical Interviews**: Create and manage interactive patient interview sessions
    * **Real-time Messaging**: Send messages and receive AI-powered patient responses
    * **Hypothesis Management**: Submit and track diagnostic hypotheses
    * **Progress Monitoring**: Live progress summaries and session notes
    * **Clinical Cases**: Manage default and custom clinical cases
    * **User Authentication**: Secure JWT-based authentication
    
    ## Getting Started
    
    1. **Authentication**: Use the `/token` endpoint to get a JWT token
    2. **Create Interview**: Start a new interview with a clinical case
    3. **Send Messages**: Exchange messages with the virtual patient
    4. **Submit Hypotheses**: Submit up to 3 diagnostic hypotheses
    5. **Monitor Progress**: Track interview progress in real-time
    """,
    version="1.0.0",
    contact={
        "name": "Virtual Patient API Support",
        "email": "support@virtualpatient.com",
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    openapi_tags=[
        {
            "name": "authentication",
            "description": "User authentication and token management"
        },
        {
            "name": "users",
            "description": "User account management"
        },
        {
            "name": "clinical-cases",
            "description": "Clinical case management and templates"
        },
        {
            "name": "medical-interviews",
            "description": "Medical interview session management"
        },
        {
            "name": "medical-interview-session-notes",
            "description": "Session notes management for medical interviews"
        },
        {
            "name": "interview-messages",
            "description": "Real-time message exchange with virtual patients"
        },
        {
            "name": "interview-hypotheses",
            "description": "Diagnostic hypothesis submission and management"
        },
        {
            "name": "interview-summary",
            "description": "Progress summary and session notes management"
        },
        {
            "name": "personalities",
            "description": "Personality management for virtual patients"
        },
        {
            "name": "medical-interview-doctor-feedback",
            "description": "Doctor feedback management for medical interviews"
        }
    ]
)

# Configure CORS. Local dev origins plus any configured public origins
# (comma-separated CORS_ALLOWED_ORIGINS), e.g. the Cloudflare tunnel UI domain.
import os

origins = [
    "http://localhost:5173",  # React app
    "http://127.0.0.1:5173",  # React app alternative
    *[origin.strip() for origin in os.getenv("CORS_ALLOWED_ORIGINS", "").split(",") if origin.strip()],
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Trace-Id"],
)

# Bind the per-request trace id (from the UI's X-Trace-Id header) so
# performance_event lines correlate frontend -> API -> worker.
from app.core.trace import TraceIdMiddleware
app.add_middleware(TraceIdMiddleware)

# Include routers
app.include_router(doctor_grading.router)
app.include_router(perception_survey.router)
app.include_router(auth.router, tags=["authentication"])
app.include_router(users.router, tags=["users"])
app.include_router(clinical_cases.router, tags=["clinical-cases"])
app.include_router(medical_interviews.router, tags=["medical-interviews"])
app.include_router(interview_performance.router)
app.include_router(medical_interview_session_notes.router, tags=["medical-interview-session-notes"])
app.include_router(medical_interview_doctor_feedback.router, tags=["medical-interview-doctor-feedback"])
app.include_router(interview_messages.router, tags=["interview-messages"])
app.include_router(interview_hypotheses.router, tags=["interview-hypotheses"])
app.include_router(summary.router, tags=["summary"])
app.include_router(personalities.router, tags=["personalities"])
app.include_router(evaluations.router, tags=["evaluations"])
app.include_router(speech.router, tags=["speech"])
app.include_router(interview_recordings.router, tags=["interview-recordings"])
app.include_router(recording_segments.router, tags=["interview-recordings"])
from app.routers import recording_turns
app.include_router(recording_turns.router, tags=["interview-recordings"])
app.include_router(calibration.router)

# Health check endpoint for Docker
@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint for Docker and load balancers"""
    return {"status": "healthy", "service": "virtual-patient-api"}

if __name__ == "__main__":

    reload = settings.environment != "production"
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0", 
        port=8000,
        reload=reload,
        reload_dirs=["app", "scripts"],
        log_level="info"
    )
