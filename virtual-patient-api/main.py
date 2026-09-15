import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.superuser import synchronize_superuser
from app.routers import (
    auth, users, organizations, clinical_cases, 
    medical_interviews, medical_interview_session_notes, medical_interview_teacher_feedback, interview_messages, interview_hypotheses, summary, personalities, evaluations, speech, interview_recordings, debug
)

@asynccontextmanager
async def lifespan(_: FastAPI):
    """Synchronize deployment-managed accounts whenever the API starts."""
    with SessionLocal() as session:
        print(synchronize_superuser(session))
    yield


app = FastAPI(
    lifespan=lifespan,
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
    * **WebSocket Support**: Real-time communication for live updates
    
    ## Getting Started
    
    1. **Authentication**: Use the `/token` endpoint to get a JWT token
    2. **Create Interview**: Start a new interview with a clinical case
    3. **Send Messages**: Exchange messages with the virtual patient
    4. **Submit Hypotheses**: Submit up to 3 diagnostic hypotheses
    5. **Monitor Progress**: Track interview progress in real-time
    
    ## WebSocket Events
    
    Connect to `/ws/medical-interviews/{interview_id}?token={token}` for real-time updates:
    
    * `gpt_typing_started` - Patient is thinking/generating response
    * `gpt_typing_stopped` - Patient finished generating response
    * `message_received` - New message received
    * `summary_updated` - Progress summary updated
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
            "name": "organizations",
            "description": "Educational institution management"
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
            "name": "medical-interview-teacher-feedback",
            "description": "Teacher feedback management for medical interviews"
        },
        {
            "name": "websocket",
            "description": "Real-time WebSocket communication for live updates"
        }
    ]
)

# Configure CORS
origins = [
    "http://localhost:5173",  # React app
    "http://127.0.0.1:5173",  # React app alternative
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Include routers
app.include_router(auth.router, tags=["authentication"])
app.include_router(users.router, tags=["users"])
app.include_router(organizations.router, tags=["organizations"])
app.include_router(clinical_cases.router, tags=["clinical-cases"])
app.include_router(medical_interviews.router, tags=["medical-interviews"])
app.include_router(medical_interview_session_notes.router, tags=["medical-interview-session-notes"])
app.include_router(medical_interview_teacher_feedback.router, tags=["medical-interview-teacher-feedback"])
app.include_router(interview_messages.router, tags=["interview-messages"])
app.include_router(interview_hypotheses.router, tags=["interview-hypotheses"])
app.include_router(summary.router, tags=["summary"])
app.include_router(personalities.router, tags=["personalities"])
app.include_router(evaluations.router, tags=["evaluations"])
app.include_router(speech.router, tags=["speech"])
app.include_router(interview_recordings.router, tags=["interview-recordings"])
app.include_router(debug.router, tags=["debug"])

# Health check endpoint for Docker
@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint for Docker and load balancers"""
    return {"status": "healthy", "service": "virtual-patient-api"}

if __name__ == "__main__":

    # Enable auto-reload in development mode
    reload = settings.environment != "production"
    
    uvicorn.run(
        "main:app",  # Use string to enable reload
        host="0.0.0.0", 
        port=8000,
        reload=reload,  # Auto-reload on file changes
        reload_dirs=["app", "scripts"],  # Watch these directories
        log_level="info"
    )
