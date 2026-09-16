"""Tests for the legacy read adapter (Requirements 28.7, 22.2).

These tests exercise the public, pure, read-only API of
``app.multimodal.legacy_adapter``:

* ``is_layered(payload)`` — shape detection.
* ``normalize_observation(payload, *, modality=None)`` — normalize one per-turn
  observation (layered or legacy flat) into the layered read view.
* ``normalize_turn(paraverbal, nonverbal_features)`` — normalize both per-turn
  modality payloads together.

The two coexisting on-disk shapes are covered without any I/O or migration:

* **Layered** — the new pipeline shape, passed through unchanged except for the
  added ``schema == "layered"`` marker.
* **Legacy flat** — the pre-refactor shape. The adapter is descriptive-only and
  must never fabricate labels: legacy families that were never computed (all
  paraverbal families except ``temporal``, and every nonverbal family) are
  surfaced as ``unavailable`` with a reason, never invented. Only the legacy
  ``interpretability.acoustic_temporal.labels.values.temporal_profile`` — which
  genuinely existed — is surfaced as the ``temporal`` integrated label.

Enum string values are referenced through the schema enums so the assertions
track the shared status/reason vocabulary. The adapter is deterministic, so
every case is a plain input -> output assertion.
"""

from __future__ import annotations

from typing import Any

from app.multimodal.legacy_adapter import (
    SCHEMA_LAYERED,
    SCHEMA_LEGACY,
    is_layered,
    normalize_observation,
    normalize_turn,
)
from app.multimodal.schemas import OutcomeStatus, UnavailableReason

# Enum string values used throughout the assertions.
_OK = OutcomeStatus.OK.value
_UNAVAILABLE = OutcomeStatus.UNAVAILABLE.value
_FEATURE_UNAVAILABLE = UnavailableReason.FEATURE_UNAVAILABLE.value

# Families the adapter must report unavailable for legacy payloads.
_PARAVERBAL_UNCOMPUTED = ("prosodic_level", "prosodic_modulation")
_NONVERBAL_FAMILIES = ("visual_orientation", "head_gestural_feedback", "facial_expressivity")


# ---------------------------------------------------------------------------
# Payload builders (deterministic plain dicts)
# ---------------------------------------------------------------------------


def _layered_paraverbal_payload() -> dict[str, Any]:
    """A new layered paraverbal payload as written by the pipeline."""
    return {
        "raw": {"f0_samples_semitones": [1.0, 2.0], "word_count": 12},
        "processed": {"speech_rate_wpm": 140.0, "pause_time_ratio": 0.2},
        "base_labels": {"temporal": {"speech_rate_wpm": {"status": _OK, "value": "typical"}}},
        "integrated_labels": {
            "temporal": {"status": _OK, "value": "measured_pace", "reason": None, "evidence": {}},
            "prosodic_level": {"status": _OK, "value": "typical_level", "reason": None, "evidence": {}},
            "prosodic_modulation": {"status": _OK, "value": "varied", "reason": None, "evidence": {}},
        },
        "quality": {"snr_db": 22.0},
        "versions": {"thresholds": "1", "label_rules": "1"},
        "config_hash": "abc123",
        "status": _OK,
        "reason": None,
    }


def _layered_nonverbal_payload() -> dict[str, Any]:
    """A new layered nonverbal payload as written by the pipeline."""
    return {
        "raw": {"face_score_samples": [0.9, 0.8]},
        "processed": {"visual_alignment_ratio": 0.7, "nod_count": 3},
        "base_labels": {"visual_orientation": {"visual_alignment_ratio": {"status": _OK, "value": "aligned"}}},
        "integrated_labels": {
            "visual_orientation": {"status": _OK, "value": "oriented", "reason": None, "evidence": {}},
            "head_gestural_feedback": {"status": _OK, "value": "responsive", "reason": None, "evidence": {}},
            "facial_expressivity": {"status": _OK, "value": "expressive", "reason": None, "evidence": {}},
        },
        "quality": {"tracked_frame_ratio": 0.95},
        "versions": {"thresholds": "1", "label_rules": "1"},
        "config_hash": "def456",
        "status": _OK,
        "reason": None,
    }


def _legacy_paraverbal_with_temporal() -> dict[str, Any]:
    """A legacy flat paraverbal payload that carries a genuine temporal_profile."""
    return {
        "speech_rate_wpm": 138.0,
        "articulation_rate_wpm": 160.0,
        "pause_time_ratio": 0.18,
        "median_pause_duration_ms": 320.0,
        "audio_quality": {"snr_db": 19.5},
        "interpretability": {
            "acoustic_temporal": {
                "labels": {
                    "status": "ok",
                    "values": {
                        "speech_rate": "typical",
                        "pause_ratio": "typical",
                        "temporal_profile": "measured_pace",
                    },
                },
                "calibration": {"baseline_used": False},
                "scope": {"context": "speaking"},
            }
        },
    }


def _legacy_paraverbal_without_temporal() -> dict[str, Any]:
    """A legacy flat paraverbal payload with no temporal_profile available."""
    return {
        "speech_rate_wpm": 138.0,
        "pause_time_ratio": 0.18,
        "audio_quality": {"snr_db": 19.5},
        "interpretability": {
            "acoustic_temporal": {
                "labels": {"status": "unavailable", "values": {}},
            }
        },
    }


def _legacy_nonverbal_flat() -> dict[str, Any]:
    """A legacy flat nonverbal payload with visual/gestural metrics only."""
    return {
        "visual_alignment_ratio": 0.66,
        "median_visual_alignment_dwell_ms": 850.0,
        "smile_activity_ratio": 0.22,
        "mean_smile_activation": 0.41,
        "nod_count": 4,
        "video_quality": {"tracked_frame_ratio": 0.92},
        "observationContext": "listening",
    }


# ---------------------------------------------------------------------------
# is_layered
# ---------------------------------------------------------------------------


def test_is_layered_true_for_processed_key() -> None:
    """A payload carrying a ``processed`` key is layered."""
    assert is_layered({"processed": {"speech_rate_wpm": 140.0}}) is True


def test_is_layered_true_for_integrated_labels_key() -> None:
    """A payload carrying an ``integrated_labels`` key is layered."""
    assert is_layered({"integrated_labels": {"temporal": {}}}) is True


def test_is_layered_false_for_legacy_flat() -> None:
    """A legacy flat payload (top-level metrics only) is not layered."""
    assert is_layered(_legacy_paraverbal_with_temporal()) is False
    assert is_layered(_legacy_nonverbal_flat()) is False


def test_is_layered_false_for_none_and_non_dict() -> None:
    """``None`` and non-dict payloads are not layered."""
    assert is_layered(None) is False
    assert is_layered([1, 2, 3]) is False  # type: ignore[arg-type]
    assert is_layered("processed") is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Layered pass-through
# ---------------------------------------------------------------------------


def test_layered_paraverbal_passthrough_preserves_all_fields() -> None:
    """A layered payload is returned unchanged except for the schema marker."""
    payload = _layered_paraverbal_payload()
    view = normalize_observation(payload)

    assert view is not None
    assert view["schema"] == SCHEMA_LAYERED
    # Every layered field is preserved verbatim.
    assert view["processed"] == payload["processed"]
    assert view["integrated_labels"] == payload["integrated_labels"]
    assert view["raw"] == payload["raw"]
    assert view["base_labels"] == payload["base_labels"]
    assert view["quality"] == payload["quality"]
    assert view["versions"] == payload["versions"]
    assert view["config_hash"] == payload["config_hash"]


def test_layered_passthrough_does_not_mutate_input() -> None:
    """Normalization is pure: the original payload gains no ``schema`` key."""
    payload = _layered_nonverbal_payload()
    view = normalize_observation(payload)

    assert view is not None
    assert view["schema"] == SCHEMA_LAYERED
    assert "schema" not in payload  # input untouched


def test_layered_ignores_modality_hint() -> None:
    """Layered payloads ignore the modality hint and stay layered."""
    payload = _layered_paraverbal_payload()
    view = normalize_observation(payload, modality="nonverbal")

    assert view is not None
    assert view["schema"] == SCHEMA_LAYERED
    assert view["integrated_labels"] == payload["integrated_labels"]


# ---------------------------------------------------------------------------
# Legacy paraverbal WITH temporal_profile
# ---------------------------------------------------------------------------


def test_legacy_paraverbal_with_temporal_surfaces_temporal_label() -> None:
    """The genuine legacy temporal_profile becomes the ``temporal`` integrated label."""
    payload = _legacy_paraverbal_with_temporal()
    view = normalize_observation(payload, modality="paraverbal")

    assert view is not None
    assert view["schema"] == SCHEMA_LEGACY

    temporal = view["integrated_labels"]["temporal"]
    assert temporal["status"] == _OK
    # The value is exactly the legacy temporal_profile, not invented.
    assert temporal["value"] == "measured_pace"
    assert temporal["reason"] is None
    # Evidence marks the origin as legacy and preserves the legacy sub-labels.
    assert temporal["evidence"]["source"] == SCHEMA_LEGACY
    assert temporal["evidence"]["labels"]["temporal_profile"] == "measured_pace"


def test_legacy_paraverbal_other_families_unavailable_not_fabricated() -> None:
    """prosodic_level and prosodic_modulation are unavailable, never fabricated."""
    view = normalize_observation(_legacy_paraverbal_with_temporal(), modality="paraverbal")

    assert view is not None
    for family in _PARAVERBAL_UNCOMPUTED:
        entry = view["integrated_labels"][family]
        assert entry["status"] == _UNAVAILABLE
        assert entry["reason"] == _FEATURE_UNAVAILABLE
        assert entry["value"] is None  # no fabricated label


def test_legacy_paraverbal_preserves_metrics_quality_and_versions() -> None:
    """Legacy top-level metrics land under processed; quality/versions/config_hash honest."""
    payload = _legacy_paraverbal_with_temporal()
    view = normalize_observation(payload, modality="paraverbal")

    assert view is not None
    processed = view["processed"]
    assert processed["speech_rate_wpm"] == 138.0
    assert processed["articulation_rate_wpm"] == 160.0
    assert processed["pause_time_ratio"] == 0.18
    # Non-metric keys are not folded into processed.
    assert "interpretability" not in processed
    assert "audio_quality" not in processed
    # Quality comes from audio_quality; versions/config_hash are unknown for legacy.
    assert view["quality"] == {"snr_db": 19.5}
    assert view["versions"] is None
    assert view["config_hash"] is None
    # The legacy interpretability block stays available for detail rendering.
    assert view["legacy_interpretability"] == payload["interpretability"]


# ---------------------------------------------------------------------------
# Legacy paraverbal WITHOUT temporal_profile
# ---------------------------------------------------------------------------


def test_legacy_paraverbal_without_temporal_is_unavailable() -> None:
    """With no temporal_profile, the temporal family is unavailable, not fabricated."""
    view = normalize_observation(_legacy_paraverbal_without_temporal(), modality="paraverbal")

    assert view is not None
    temporal = view["integrated_labels"]["temporal"]
    assert temporal["status"] == _UNAVAILABLE
    assert temporal["value"] is None
    assert temporal["reason"] == _FEATURE_UNAVAILABLE


# ---------------------------------------------------------------------------
# Legacy nonverbal flat
# ---------------------------------------------------------------------------


def test_legacy_nonverbal_flat_families_all_unavailable() -> None:
    """Every nonverbal family is unavailable for legacy flat data, never fabricated."""
    view = normalize_observation(_legacy_nonverbal_flat(), modality="nonverbal")

    assert view is not None
    assert view["schema"] == SCHEMA_LEGACY
    for family in _NONVERBAL_FAMILIES:
        entry = view["integrated_labels"][family]
        assert entry["status"] == _UNAVAILABLE
        assert entry["reason"] == _FEATURE_UNAVAILABLE
        assert entry["value"] is None  # no fabricated label


def test_legacy_nonverbal_flat_preserves_metrics_and_quality() -> None:
    """Legacy nonverbal metrics land under processed; quality from video_quality."""
    view = normalize_observation(_legacy_nonverbal_flat(), modality="nonverbal")

    assert view is not None
    processed = view["processed"]
    assert processed["visual_alignment_ratio"] == 0.66
    assert processed["smile_activity_ratio"] == 0.22
    assert processed["nod_count"] == 4
    assert "video_quality" not in processed
    assert "observationContext" not in processed
    assert view["quality"] == {"tracked_frame_ratio": 0.92}
    assert view["versions"] is None
    assert view["config_hash"] is None


# ---------------------------------------------------------------------------
# Modality inference (no hint)
# ---------------------------------------------------------------------------


def test_modality_inference_detects_nonverbal() -> None:
    """A legacy nonverbal payload with no modality hint is detected as nonverbal."""
    view = normalize_observation(_legacy_nonverbal_flat())

    assert view is not None
    assert view["schema"] == SCHEMA_LEGACY
    assert view["modality"] == "nonverbal"
    # Nonverbal families present -> confirms nonverbal branch was taken.
    assert set(view["integrated_labels"]) == set(_NONVERBAL_FAMILIES)


def test_modality_inference_detects_paraverbal() -> None:
    """A legacy paraverbal payload with no modality hint is detected as paraverbal."""
    view = normalize_observation(_legacy_paraverbal_with_temporal())

    assert view is not None
    assert view["schema"] == SCHEMA_LEGACY
    assert view["modality"] == "paraverbal"
    assert "temporal" in view["integrated_labels"]


# ---------------------------------------------------------------------------
# None -> None
# ---------------------------------------------------------------------------


def test_none_payload_returns_none() -> None:
    """A patient turn's absent paraverbal layer stays absent."""
    assert normalize_observation(None) is None
    assert normalize_observation(None, modality="paraverbal") is None


# ---------------------------------------------------------------------------
# normalize_turn
# ---------------------------------------------------------------------------


def test_normalize_turn_returns_both_views() -> None:
    """normalize_turn normalizes both modality payloads with correct modalities."""
    result = normalize_turn(
        _legacy_paraverbal_with_temporal(),
        _legacy_nonverbal_flat(),
    )

    para = result["paraverbal"]
    nonverbal = result["nonverbal_features"]
    assert para is not None and nonverbal is not None
    assert para["modality"] == "paraverbal"
    assert nonverbal["modality"] == "nonverbal"
    assert para["integrated_labels"]["temporal"]["value"] == "measured_pace"


def test_normalize_turn_absent_paraverbal_patient_turn() -> None:
    """A patient turn has no paraverbal layer; nonverbal is still normalized."""
    result = normalize_turn(None, _legacy_nonverbal_flat())

    assert result["paraverbal"] is None
    assert result["nonverbal_features"] is not None
    assert result["nonverbal_features"]["modality"] == "nonverbal"


# ---------------------------------------------------------------------------
# Global no-fabrication guarantee
# ---------------------------------------------------------------------------


def test_no_fabricated_labels_anywhere() -> None:
    """Uncomputed families never carry a value across all legacy views."""
    views = [
        normalize_observation(_legacy_paraverbal_with_temporal(), modality="paraverbal"),
        normalize_observation(_legacy_paraverbal_without_temporal(), modality="paraverbal"),
        normalize_observation(_legacy_nonverbal_flat(), modality="nonverbal"),
    ]
    for view in views:
        assert view is not None
        for family, entry in view["integrated_labels"].items():
            if entry["status"] != _OK:
                # An unavailable family must never carry a value.
                assert entry["value"] is None, f"fabricated value for {family}"
