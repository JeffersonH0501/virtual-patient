"""Conservative engineering eligibility; these limits are not clinical cutoffs."""
QUALITY_POLICY_VERSION = "signal_eligibility_v3_family_and_nod_windows"
MIN_VISUAL_SAMPLES = 3
MIN_VISUAL_COVERAGE = 0.8

REFERENCE_FEATURE_FAMILIES = {
    "median_loudness": "prosodic_level",
    "loudness_p20_p80_range": "prosodic_variability",
    "nod_rate_min": "head_nods",
    "mean_smile_activation": "smile_activity",
}


def reference_feature_available(raw, feature: str) -> bool:
    """Use the same signal admission before references and final labels."""
    if raw is None or feature not in REFERENCE_FEATURE_FAMILIES:
        return False
    values = raw.model_dump()
    return family_evidence_available({"raw": values,
        "quality": values.get("audio_quality", values.get("video_quality", {}))},
        REFERENCE_FEATURE_FAMILIES[feature])


def family_evidence_available(payload: dict | None, family: str) -> bool:
    if not payload or payload.get("status") not in (None, "ok"):
        return False
    quality = payload.get("quality") or {}
    if family in {"speech_timing", "prosodic_level", "prosodic_variability"}:
        issues = set(quality.get("issues", []))
        return not (issues & {"insufficient_voiced_duration", "clipping_unusable"} or
                    family == "speech_timing" and "truncated_audio" in issues)
    raw = payload.get("raw") or {}
    duration = raw.get("turn_duration_ms")
    if family in {'gaze_orientation', 'smile_activity'} and quality.get('evaluable_gaze_ms' if family == 'gaze_orientation' else 'evaluable_smile_ms') is not None:
        valid_ms = quality['evaluable_gaze_ms' if family == 'gaze_orientation' else 'evaluable_smile_ms']
        return isinstance(duration, (int, float)) and duration > 0 and valid_ms / duration >= MIN_VISUAL_COVERAGE
    if family == "head_nods" and quality.get("nod_evaluable_ms") is not None:
        eligible_ms = quality.get("nod_eligible_ms")
        valid_ms = quality["nod_evaluable_ms"]
        return (isinstance(eligible_ms, (int, float)) and eligible_ms > 0 and
                isinstance(valid_ms, (int, float)) and valid_ms >= 7 * 1000 / 30 and
                valid_ms / eligible_ms >= MIN_VISUAL_COVERAGE)
    fps = raw.get("sample_fps")
    expected = quality.get("expected_frames")
    if expected is None and duration is not None and fps is not None:
        expected = duration * fps / 1000
    valid_key = {"gaze_orientation": "valid_gaze_frames", "smile_activity": "valid_smile_frames", "head_nods": "valid_nod_predictions"}.get(family)
    if not valid_key or not isinstance(expected, (int, float)) or expected <= 0:
        return False
    valid = quality.get(valid_key)
    if not isinstance(valid, (int, float)):
        return False
    return valid >= MIN_VISUAL_SAMPLES and valid / expected >= MIN_VISUAL_COVERAGE
