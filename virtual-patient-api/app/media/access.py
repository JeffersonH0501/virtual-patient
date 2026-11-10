"""Shared authorization and private streaming for interview media."""
import logging
import re
from typing import Annotated, Optional
from fastapi import Cookie, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import inspect
from sqlalchemy.orm import Session
from app.core.auth import get_current_user_from_token
from app.core.database import get_db
from app.core.review_access import can_replay
from app.models.medical_interview import MedicalInterviewDB
from app.models.user import UserDB, UserRole
logger = logging.getLogger(__name__)
RANGE_PATTERN = re.compile(r'^bytes=(\d*)-(\d*)$')
ALLOWED_CONTENT_TYPES = {'audio/webm': '.webm', 'audio/ogg': '.ogg', 'audio/mp4': '.m4a', 'video/webm': '.webm', 'video/mp4': '.mp4'}

def _current_media_user(
    authorization: Annotated[Optional[str], Header()] = None,
    access_token: Annotated[Optional[str], Cookie()] = None,
    media_access_token: Annotated[Optional[str], Cookie()] = None,
    db: Session = Depends(get_db),
) -> UserDB:
    token = media_access_token or access_token
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    user = get_current_user_from_token(token, db)
    if user is None or user.disabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return user


def _get_interview(db: Session, interview_id: int) -> MedicalInterviewDB:
    interview = db.query(MedicalInterviewDB).filter(MedicalInterviewDB.id == interview_id).first()
    if interview is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
    return interview


def _require_owner(interview: MedicalInterviewDB, user: UserDB) -> None:
    if interview.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the interview owner can modify its recording")


def _require_replay_access(interview: MedicalInterviewDB, user: UserDB) -> None:
    if interview.user_id == user.id:
        return
    owner_organization_id = interview.user.organization_id if interview.user else None
    if user.role == UserRole.SUPERUSER and user.organization_id is not None and user.organization_id == owner_organization_id:
        return
    state = inspect(interview, raiseerr=False)
    db = state.session if state is not None else None
    if db is not None and can_replay(db, interview, user):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Recording access denied")


def _require_completed_for_replay(interview: MedicalInterviewDB, *, allow_processing: bool = False) -> None:
    # Frozen capture can be replayed for independent self-assessment before feedback is ready.
    if interview.status != "completed" and not (allow_processing and interview.status == "processing"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Interview results are not ready yet",
        )


def _discard_saved_media(db, storage, storage_keys, *, attempted_model=None):
    if storage_keys and attempted_model is not None:
        # A connection failure can be reported after PostgreSQL commits.
        try:
            column = attempted_model.storage_key
            confirmed = {key for key, in db.query(column).filter(column.in_(storage_keys))}
        except Exception:
            logger.warning("Unable to verify media commit; retaining files for expiry", exc_info=True)
            return
        storage_keys = [key for key in storage_keys if key not in confirmed]
    for storage_key in storage_keys:
        try:
            storage.delete(storage_key)
        except OSError:
            logger.warning("Unable to remove uncommitted media file", exc_info=True)


def _stream_private_media(storage, path, request, content_type):
    file_size = path.stat().st_size
    range_header = request.headers.get("range")
    start, end, response_status = _parse_range(range_header, file_size)
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
        "Cache-Control": "private, no-store",
    }
    if response_status == status.HTTP_206_PARTIAL_CONTENT:
        headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
    return StreamingResponse(
        storage.iter_range(path, start, end),
        status_code=response_status,
        media_type=content_type,
        headers=headers,
    )


def _parse_range(range_header: Optional[str], file_size: int) -> tuple[int, int, int]:
    if file_size <= 0:
        return 0, -1, status.HTTP_200_OK
    if not range_header:
        return 0, file_size - 1, status.HTTP_200_OK
    match = RANGE_PATTERN.match(range_header.strip())
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{file_size}"},
        )
    start_text, end_text = match.groups()
    if not start_text and not end_text:
        raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE)
    if start_text:
        start = int(start_text)
        end = int(end_text) if end_text else file_size - 1
    else:
        suffix_length = int(end_text)
        start = max(file_size - suffix_length, 0)
        end = file_size - 1
    if start >= file_size or start > end:
        raise HTTPException(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{file_size}"},
        )
    return start, min(end, file_size - 1), status.HTTP_206_PARTIAL_CONTENT

