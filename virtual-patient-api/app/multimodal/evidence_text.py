"""Render eligible behavioral observations with their relevant denominators."""

from .label_glossary import LABEL_GLOSSARY
from .quality_policy import family_evidence_available

NEUTRAL_ABSENCE_LABELS = frozenset({"no_nodding", "absent_smile_activity"})


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
        text = f"Estimated gaze inside the interaction area or toward the calibrated camera: {processed['interaction_gaze_ratio'] * 100:.1f}% of evaluable visual time."
        samples = raw.get("gaze_semantic_observations") or []
        fps = raw.get("sample_fps")
        end = (raw.get("extractor") or {}).get("window_end_ms")
        if samples and isinstance(fps, (int, float)) and fps > 0 and isinstance(end, (int, float)):
            from app.nonverbal.preprocessing import time_weighted_states
            for reason, label in (("eyes_closed", "closed eyes"), ("face_not_detected", "face not detected")):
                states = [{"timestamp_ms": item["timestamp_ms"], "state": "INSIDE" if item.get("reason") == reason and item.get("state") == "OUTSIDE" else "UNAVAILABLE"} for item in samples]
                totals, _ = time_weighted_states(states, end_ms=end, max_support_ms=min(200., 1000. / fps))
                if totals["INSIDE"]:
                    text += f" Outside interaction due to {label}: {totals['INSIDE'] / 1000:.2f} seconds."
        return text
    if family == "head_nods" and processed.get("nod_count") is not None and raw.get("turn_duration_ms") is not None:
        return f"Detected {processed['nod_count']} nods during a {raw['turn_duration_ms'] / 1000:.1f} second turn."
    if family == "smile_activity" and processed.get("smile_activity_ratio") is not None:
        return f"{description} {processed['smile_activity_ratio'] * 100:.1f}% of evaluable facial time."
    if family == "speech_timing":
        metrics = []
        if processed.get("speech_rate_wpm") is not None:
            metrics.append(f"{processed['speech_rate_wpm']:.1f} words per minute")
        if processed.get("pause_count") is not None:
            metrics.append(f"{processed['pause_count']} internal pauses of at least 500 ms")
        if label == "intermittent_by_long_pauses" and processed.get("median_pause_duration_ms") is not None:
            metrics.append(f"median pause {processed['median_pause_duration_ms'] / 1000:.2f} seconds")
        if processed.get("pause_time_ratio") is not None:
            metrics.append(f"{processed['pause_time_ratio'] * 100:.1f}% of the speech window in reportable pauses")
        issues = (payload.get("quality") or {}).get("issues", [])
        boundary_note = (" Speech was detected at a window boundary; completeness of the speech and transcript is uncertain."
                         if "speech_at_window_start" in issues or "speech_at_window_end" in issues else "")
        return description + (" " + "; ".join(metrics) + "." if metrics else "") + boundary_note
    if family == "prosodic_variability" and processed.get("f0_p20_p80_range_semitones") is not None:
        return f"{description} F0 P20–P80 range: {processed['f0_p20_p80_range_semitones']:.2f} semitones."
    return description
