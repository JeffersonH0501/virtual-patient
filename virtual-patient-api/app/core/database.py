import asyncio
from contextlib import asynccontextmanager
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

SQLALCHEMY_DATABASE_URL = settings.database_url

# Pool sized for concurrent interviews: each turn briefly uses several pooled
# connections (claim tx, checkpointer reads, commit) across threadpool hops.
# Each Python process can open up to pool_size + max_overflow connections.
# Account for API workers, visual workers, and isolated child processes when
# sizing PostgreSQL. pre_ping drops dead connections; recycle avoids stale idle
# connections.
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_size=10,
    max_overflow=10,
    pool_timeout=30,
    pool_pre_ping=True,
    pool_recycle=1800,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Reserve most connections for short requests and durable workers. Admission
# precedes request DB dependencies so rejected calls do not check out a connection.
_external_transaction_slots = asyncio.Semaphore(4)


async def admit_external_transaction():
    if _external_transaction_slots.locked():
        raise HTTPException(503, "Interview service is busy; retry", headers={"Retry-After": "1"})
    async with _external_transaction_slots:
        yield


# Leave at least two external transaction slots for patient replies.
_review_transaction_slots = asyncio.Semaphore(2)


async def admit_review_transaction():
    if _review_transaction_slots.locked():
        raise HTTPException(503, "Review service is busy; retry", headers={"Retry-After": "1"})
    async with _review_transaction_slots, asynccontextmanager(admit_external_transaction)():
        yield
