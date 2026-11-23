"""Validated accessors for the visual calibration stored on an interview."""
from typing import Any, Protocol
from app.multimodal.schemas import PersonalBaseline

class _MetadataCarrier(Protocol):
    """Minimal interface for the read helper: anything exposing metadata.

    Both the ORM ``MedicalInterviewDB`` and the pydantic ``MedicalInterview``
    expose ``interview_metadata``; the helper only needs that attribute.
    """

    interview_metadata: dict[str, Any] | None


def read_personal_baseline(interview: _MetadataCarrier | None, *, segment=None) -> PersonalBaseline | None:
    """Read and validate the stored baseline; the single pipeline accessor.

    Parses ``interview_metadata.calibration.personal_baseline`` and validates it
    against the :class:`PersonalBaseline` schema. Returns ``None`` when no
    baseline is stored or the stored payload does not satisfy the schema, so the
    pipeline can treat a missing/invalid baseline as ``missing_calibration``
    without scattering nested-dict access across the codebase.
    """
    calibration = read_calibration(interview, segment=segment) or {}
    if calibration.get("status") == "without_gaze":
        return None
    stored = calibration.get("personal_baseline")
    if not isinstance(stored, dict):
        return None
    try:
        return PersonalBaseline.model_validate(stored)
    except Exception:
        # A stored payload that does not satisfy the schema is treated as no
        # baseline rather than raising, so the pipeline degrades gracefully.
        return None


def read_calibration_profile(interview: _MetadataCarrier | None, *, segment=None) -> dict[str, Any] | None:
    """Read the stored calibration ``profile`` dict from the interview metadata.

    The profile holds the gaze affine matrix and other visual references the
    multimodal pipeline needs to reconstruct the participant-specific gaze
    tracker. It lives alongside the personal baseline under
    ``interview_metadata.calibration``. Returns ``None`` when no profile is
    stored so the pipeline marks gaze unavailable while retaining other signals.
    """
    calibration = read_calibration(interview, segment=segment) or {}
    if calibration.get("status") == "without_gaze":
        return None
    profile = calibration.get("profile")
    if not isinstance(profile, dict) or profile.get("gaze_source") != "mediapipe_five_point_v1":
        return None
    geometry = profile.get("capture_geometry") if isinstance(profile, dict) else None
    source = segment if segment is not None else getattr(interview, "recording", None)
    capture = getattr(source, "capture_config", None) or {}
    if geometry is not None:
        recorded_geometry = capture.get("geometry")
        if capture.get("geometryStable") is False or not isinstance(recorded_geometry, dict):
            return None
        if any(recorded_geometry.get(key) != geometry.get(key) for key in (
            "viewport_width", "viewport_height", "device_pixel_ratio", "video_width", "video_height",
        )):
            return None
    return profile if isinstance(profile, dict) else None


def read_calibration(interview: _MetadataCarrier | None, *, segment=None) -> dict[str, Any] | None:
    """Read the stored calibration block from ``interview_metadata.calibration``.

    This is the single accessor for the whole persisted calibration record (its
    ``status``, ``profile``, ``personal_baseline`` and remaining metadata), so
    callers that need the block itself do not scatter nested-dict access across
    the codebase. Returns ``None`` when no calibration block is stored.
    """
    if segment is not None:
        calibration = segment.calibration
    else:
        metadata = getattr(interview, "interview_metadata", None) or {}
        calibration = metadata.get("calibration")
    return calibration if isinstance(calibration, dict) else None


def calibration_allows_capture(calibration: dict | None) -> bool:
    """Accept a verified profile or the server-authorized preparation without gaze."""
    if not calibration:
        return False
    if calibration.get("status") == "without_gaze":
        return (calibration.get("version") == "multimodal_without_gaze_v1"
                and len(set(calibration.get("failed_capture_ids") or [])) >= 2
                and bool((calibration.get("profile") or {}).get("capture_geometry")))
    return calibration.get("status") == "passed"


def calibration_passed(interview: _MetadataCarrier | None) -> bool:
    """Report whether calibration or an explicit no-gaze authorization allows start."""
    calibration = read_calibration(interview)
    return calibration_allows_capture(calibration) and (
        calibration.get("status") == "without_gaze" or read_personal_baseline(interview) is not None)


