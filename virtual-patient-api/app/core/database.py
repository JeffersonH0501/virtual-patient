import asyncio
from contextlib import asynccontextmanager
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

SQLALCHEMY_DATABASE_URL = settings.database_url

engine = create_engine(SQLALCHEMY_DATABASE_URL)
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
