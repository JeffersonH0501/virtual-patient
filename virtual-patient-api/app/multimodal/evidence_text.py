"""Render eligible behavioral observations compactly for the evaluator.

Only the representation sent to the model is shaped here. The persisted measurements, thresholds and labels are
untouched. The turn duration is not repeated per family: the conversation formatter states it once in the turn header.
"""
from .label_glossary import LABEL_GLOSSARY
from .quality_policy import family_evidence_available
NEUTRAL_ABSENCE_LABELS = frozenset({"no_nodding", "absent_smile_activity"})
# Closed eyes or a missing face shorter than this is ordinary blinking and tracking noise, not worth the reader's attention.
MIN_NOTABLE_OUTSIDE_SECONDS = 0.5
def _percent(ratio: float) -> str:
    """Whole percentages: the precision of these estimates does not justify decimals, and a trace is not zero."""
    percent = ratio * 100
    if percent <= 0:
        return "0%"
    return "<1%" if percent < 1 else f"{round(percent)}%"
def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"
def _gaze(label: str, processed: dict, raw: dict, description: str) -> str:
    share = _percent(processed["interaction_gaze_ratio"])
    if label == "interaction_gaze_inside":
        text = f"Gaze mostly toward the interaction area or calibrated camera ({share} of the analysed time)."
    elif label == "interaction_gaze_outside":
        text = f"Gaze mostly away from the interaction area ({share} toward it or the calibrated camera)."
    else:
        text = f"{description} ({share} toward the interaction area or calibrated camera)."
    samples = raw.get("gaze_semantic_observations") or []
    fps = raw.get("sample_fps")
    end = (raw.get("extractor") or {}).get("window_end_ms")
    if samples and isinstance(fps, (int, float)) and fps > 0 and isinstance(end, (int, float)):
        from app.nonverbal.preprocessing import time_weighted_states
        notes = []
        for reason, name in (("eyes_closed", "closed eyes"), ("face_not_detected", "face not detected")):
            states = [{"timestamp_ms": item["timestamp_ms"], "state": "INSIDE" if item.get("reason") == reason and item.get("state") == "OUTSIDE" else "UNAVAILABLE"} for item in samples]
            totals, _ = time_weighted_states(states, end_ms=end, max_support_ms=min(200., 1000. / fps))
            if totals["INSIDE"] / 1000 >= MIN_NOTABLE_OUTSIDE_SECONDS:
                notes.append(name)
        if notes:
            text += f" The time away includes {' and '.join(notes)}."
    return text
def _speech_timing(processed: dict, description: str, issues: list) -> str:
    details = []
    pauses = processed.get("pause_count")
    if pauses:
        details.append(f"{_count(pauses, 'internal pause')} of at least 500 ms")
    boundary = (" Speech was detected at a window boundary, so the speech and its transcript may be incomplete."
                if "speech_at_window_start" in issues or "speech_at_window_end" in issues else "")
    return description + (" " + "; ".join(details) + "." if details else "") + boundary
def render_family_evidence(payload: dict, family: str) -> str | None:
    outcome = (payload.get("integrated_labels") or {}).get(family) or {}
    label = outcome.get("value")
    if outcome.get("status") != "ok" or label not in LABEL_GLOSSARY or label == "unavailable" or not family_evidence_available(payload, family):
        return None
    # Absence of a behavior (no nods, no smile) is neutral: it is not rendered as evidence.
    if label in NEUTRAL_ABSENCE_LABELS:
        return None
    description = LABEL_GLOSSARY[label]
    if family in {"prosodic_level", "prosodic_variability"} and "truncated_audio" in (payload.get("quality") or {}).get("issues", []):
        description += " The audio was truncated; this describes only the decoded portion."
    processed = payload.get("processed") or {}
    raw = payload.get("raw") or {}
    if family == "gaze_orientation" and processed.get("interaction_gaze_ratio") is not None:
        return _gaze(label, processed, raw, description)
    if family == "head_nods" and processed.get("nod_count") is not None:
        return f"{_count(processed['nod_count'], 'head nod')} detected."
    if family == "speech_timing":
        return _speech_timing(processed, description, (payload.get("quality") or {}).get("issues", []))
    # Prosodic level and modulation are described by their label only: their raw values (loudness on an arbitrary
    # scale, F0 range in semitones) carry no meaning for the reader without the thresholds, which are not shared.
    return description
