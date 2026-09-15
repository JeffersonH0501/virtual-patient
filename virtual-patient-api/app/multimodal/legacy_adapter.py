"""Backend read helper that normalizes legacy flat per-turn JSON.

Requirements 22.1, 22.2, 23.1, 23.2 (design section "Backward compatibility &
cross-codebase references").

Two per-turn observation shapes coexist in ``interview_turns.paraverbal`` and
``interview_turns.nonverbal_features`` without any destructive migration
(Requirement 22.3, 23):

* **Layered** — the new shape written by the pipeline
  (``app/multimodal/pipeline.py`` ``_layer_to_json``): ``raw`` / ``processed`` /
  ``base_labels`` / ``integrated_labels`` / ``quality`` / ``versions`` /
  ``config_hash`` / ``status`` / ``reason``.
* **Legacy flat** — the pre-refactor shape (``Legacy_Result``):
  - paraverbal: top-level derived metrics (``speech_rate_wpm``,
    ``pause_time_ratio``, ...) plus an ``interpretability.acoustic_temporal``
    block whose ``labels.values.temporal_profile`` is the only genuinely
    computed integrated label.
  - nonverbal: top-level derived metrics (``visual_alignment_ratio``,
    ``median_visual_alignment_dwell_ms``, ``smile_activity_ratio``,
    ``mean_smile_activation``, ``nod_count``, ...) plus ``observationContext``
    and ``video_quality``.

This module exposes a small, pure, read-only normalizer that maps either shape
onto the layered read shape so the API/recap and the frontend adapter can render
both. It is descriptive-only and never fabricates labels: legacy families that
were never computed (all paraverbal families except ``temporal``, and every
nonverbal family) are surfaced as ``unavailable`` with a reason, not invented.
Only the legacy ``temporal_profile`` — which genuinely existed — is surfaced as
the ``temporal`` integrated label.

The adapter performs no I/O and mutates nothing; it returns fresh dicts.
"""

from __future__ import annotations

from typing import Any

from app.multimodal.schemas import OutcomeStatus, UnavailableReason

__all__ = [
    "SCHEMA_LAYERED",
    "SCHEMA_LEGACY",
    "normalize_observation",
    "normalize_turn",
    "is_layered",
]

# Marker recorded on every normalized view so consumers (and task 9.2's frontend
# adapter) can tell how a payload was interpreted without re-detecting the shape.
SCHEMA_LAYERED = "layered"
SCHEMA_LEGACY = "legacy"

# Keys that unambiguously identify the layered shape written by the pipeline.
# ``processed`` and ``integrated_labels`` are the design-mandated detection keys
# (design: "if ``processed``/``integrated_labels`` keys exist it is layered").
_LAYERED_MARKER_KEYS = ("processed", "integrated_labels")

# Legacy paraverbal integrated label lived here:
# ``interpretability.acoustic_temporal.labels.values.temporal_profile``.
_LEGACY_TEMPORAL_BLOCK = "acoustic_temporal"

# Nonverbal families the legacy flat shape never computed. They must be reported
# unavailable, never fabricated.
_NONVERBAL_FAMILIES = (
    "visual_orientation",
    "head_gestural_feedback",
    "facial_expressivity",
)
# Paraverbal families the legacy flat shape never computed as integrated labels.
# ``temporal`` is handled separately because ``temporal_profile`` genuinely
# existed.
_PARAVERBAL_UNCOMPUTED_FAMILIES = ("prosodic_level", "prosodic_modulation")


def is_layered(payload: dict[str, Any] | None) -> bool:
    """Return ``True`` when ``payload`` already uses the layered shape.

    Detection follows the design contract: a payload carrying a ``processed`` or
    ``integrated_labels`` key is treated as layered. Legacy flat payloads never
    carry those keys (their metrics sit at the top level).
    """
    if not isinstance(payload, dict):
        return False
    return any(key in payload for key in _LAYERED_MARKER_KEYS)


def _unavailable_family(
    reason: UnavailableReason = UnavailableReason.FEATURE_UNAVAILABLE,
) -> dict[str, Any]:
    """Build an ``unavailable`` integrated-label entry with an explanation.

    Used for legacy families that were never computed. It carries no value, so
    no label is fabricated (Requirement 24.3), and an explicit reason so the gap
    is explained rather than an unexplained null.
    """
    return {
        "status": OutcomeStatus.UNAVAILABLE.value,
        "value": None,
        "reason": reason.value,
        "evidence": {},
    }


def _legacy_temporal_integrated_label(payload: dict[str, Any]) -> dict[str, Any]:
    """Surface the legacy ``temporal_profile`` as the ``temporal`` integrated label.

    The legacy paraverbal payload stored the only genuinely computed integrated
    label at ``interpretability.acoustic_temporal.labels.values.temporal_profile``.
    When present, it is surfaced as the ``temporal`` family value with the
    supporting legacy label values kept as evidence. When absent, the family is
    reported unavailable rather than invented.
    """
    interpretability = payload.get("interpretability")
    if not isinstance(interpretability, dict):
        return _unavailable_family()
    block = interpretability.get(_LEGACY_TEMPORAL_BLOCK)
    if not isinstance(block, dict):
        return _unavailable_family()
    labels = block.get("labels")
    values = labels.get("values") if isinstance(labels, dict) else None
    if not isinstance(values, dict):
        return _unavailable_family()
    temporal_profile = values.get("temporal_profile")
    if temporal_profile is None:
        return _unavailable_family()
    return {
        "status": OutcomeStatus.OK.value,
        "value": temporal_profile,
        "reason": None,
        # Preserve the legacy sub-labels and calibration marker as evidence so
        # the origin of the label stays traceable; this is genuine legacy data,
        # not a fabrication.
        "evidence": {
            "source": SCHEMA_LEGACY,
            "labels": values,
            "calibration": block.get("calibration"),
            "labels_status": labels.get("status") if isinstance(labels, dict) else None,
        },
    }


def _normalize_layered(payload: dict[str, Any]) -> dict[str, Any]:
    """Lightly normalize an already-layered payload into the read view.

    The layered shape is passed through unchanged so new structured data flows to
    consumers exactly as persisted. Only a ``schema`` marker is added (in a fresh
    dict) so the read view is uniform across both shapes.
    """
    view = dict(payload)
    view["schema"] = SCHEMA_LAYERED
    return view


def _normalize_legacy_paraverbal(payload: dict[str, Any]) -> dict[str, Any]:
    """Wrap a legacy flat paraverbal payload into the layered read shape.

    The legacy top-level derived metrics become ``processed`` verbatim (nothing
    is dropped), ``raw`` is ``None`` (legacy did not persist raw sample arrays in
    a layered form), ``quality`` is taken from the legacy ``audio_quality`` when
    present, and ``versions``/``config_hash`` are ``None`` because legacy rows
    predate config traceability. Integrated labels are honest: ``temporal`` from
    the legacy ``temporal_profile`` when present, the other families unavailable.
    """
    processed = {
        key: value
        for key, value in payload.items()
        if key not in ("interpretability", "audio_quality", "observationContext")
    }
    integrated = {"temporal": _legacy_temporal_integrated_label(payload)}
    for family in _PARAVERBAL_UNCOMPUTED_FAMILIES:
        integrated[family] = _unavailable_family()

    interpretability = payload.get("interpretability")
    context = payload.get("observationContext")
    if context is None and isinstance(interpretability, dict):
        block = interpretability.get(_LEGACY_TEMPORAL_BLOCK)
        if isinstance(block, dict):
            scope = block.get("scope")
            if isinstance(scope, dict):
                context = scope.get("context")

    return {
        "schema": SCHEMA_LEGACY,
        "modality": "paraverbal",
        "raw": None,
        "processed": processed,
        "base_labels": None,
        "integrated_labels": integrated,
        "quality": payload.get("audio_quality") or {},
        "versions": None,
        "config_hash": None,
        "status": OutcomeStatus.OK.value,
        "reason": None,
        # Keep the original legacy interpretability block available so a detail
        # view can still show the legacy temporal reasoning verbatim.
        "legacy_interpretability": interpretability,
        "context": context,
    }


def _normalize_legacy_nonverbal(payload: dict[str, Any]) -> dict[str, Any]:
    """Wrap a legacy flat nonverbal payload into the layered read shape.

    The legacy top-level derived metrics become ``processed`` verbatim,
    ``quality`` is taken from the legacy ``video_quality`` when present, and every
    nonverbal integrated family is reported unavailable because the legacy flat
    shape never produced nonverbal integrated labels. No nonverbal label is
    fabricated.
    """
    processed = {
        key: value
        for key, value in payload.items()
        if key not in ("video_quality", "observationContext")
    }
    integrated = {family: _unavailable_family() for family in _NONVERBAL_FAMILIES}
    return {
        "schema": SCHEMA_LEGACY,
        "modality": "nonverbal",
        "raw": None,
        "processed": processed,
        "base_labels": None,
        "integrated_labels": integrated,
        "quality": payload.get("video_quality") or {},
        "versions": None,
        "config_hash": None,
        "status": OutcomeStatus.OK.value,
        "reason": None,
        "context": payload.get("observationContext"),
    }


def _looks_like_nonverbal(payload: dict[str, Any]) -> bool:
    """Heuristically decide whether a legacy flat payload is nonverbal.

    Legacy nonverbal payloads carry visual/gestural metrics; legacy paraverbal
    payloads carry speech metrics and (usually) an ``interpretability`` block.
    The check is only used when the caller does not already know the modality.
    """
    nonverbal_markers = (
        "visual_alignment_ratio",
        "median_visual_alignment_dwell_ms",
        "smile_activity_ratio",
        "mean_smile_activation",
        "nod_count",
        "nod_rate_min",
        "video_quality",
    )
    return any(marker in payload for marker in nonverbal_markers)


def normalize_observation(
    payload: dict[str, Any] | None,
    *,
    modality: str | None = None,
) -> dict[str, Any] | None:
    """Normalize a stored per-turn observation payload into the read shape.

    Accepts either the new layered shape or a legacy flat shape and returns a
    consistent, renderable read view. Returns ``None`` for ``None`` (a patient
    turn's paraverbal layer, or an absent observation) so absence stays absent.

    The function is pure and read-only: it never mutates ``payload`` and performs
    no I/O.

    Args:
        payload: The stored per-turn JSON (layered or legacy flat), or ``None``.
        modality: Optional ``"paraverbal"`` / ``"nonverbal"`` hint used only when
            the payload is legacy flat and its modality cannot be inferred from
            its fields. Layered payloads ignore this hint.

    Returns:
        A layered read view with a ``schema`` marker (``"layered"`` or
        ``"legacy"``), or ``None``.
    """
    if payload is None:
        return None
    if not isinstance(payload, dict):
        # Defensive: unexpected scalar/list payloads are returned untouched so a
        # single malformed row never raises during read.
        return payload

    if is_layered(payload):
        return _normalize_layered(payload)

    resolved_modality = modality
    if resolved_modality is None:
        resolved_modality = "nonverbal" if _looks_like_nonverbal(payload) else "paraverbal"

    if resolved_modality == "nonverbal":
        return _normalize_legacy_nonverbal(payload)
    return _normalize_legacy_paraverbal(payload)


def normalize_turn(
    paraverbal: dict[str, Any] | None,
    nonverbal_features: dict[str, Any] | None,
) -> dict[str, Any]:
    """Normalize both per-turn modality payloads together.

    Convenience wrapper for the recap/turn path, which holds the two columns and
    already knows each one's modality. Returns a dict with normalized
    ``paraverbal`` and ``nonverbal_features`` views (either may be ``None``).
    """
    return {
        "paraverbal": normalize_observation(paraverbal, modality="paraverbal"),
        "nonverbal_features": normalize_observation(
            nonverbal_features, modality="nonverbal"
        ),
    }
