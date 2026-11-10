"""Declarative threshold engine: processed features -> base labels (Requirement 11).

This module maps :class:`~app.multimodal.schemas.ParaverbalProcessedFeatures` and
:class:`~app.multimodal.schemas.NonverbalProcessedFeatures` to per-feature base
labels using the strategy tables declared in ``thresholds.yaml``. It is the
Threshold stage of the multimodal pipeline.

Design boundaries preserved here (Requirement 11.1-11.4, 12.3):

* Declarative. Each feature's threshold entry carries a ``strategy`` field, and
  the engine resolves it through a small dispatch table (:data:`_STRATEGIES`).
  There is no per-feature ``if/elif`` branching and no signal-specific code.
* Config-driven only. The engine reads processed *feature names* and the
  ``thresholds`` section of the loaded :class:`MethodologyConfig`. It never
  references OpenSMILE, MediaPipe, media, or raw feature internals.
* Descriptive-only. The produced labels are behavioural/contextual observations
  (the raw strings declared in the config), never measures of empathy,
  attention, warmth, or any psychological state.
* No fabrication. A missing or ``None`` processed feature yields a
  :class:`~app.multimodal.schemas.FamilyLabel` with
  ``status=UNAVAILABLE`` / ``reason=FEATURE_UNAVAILABLE``; a strategy whose
  prerequisites are absent (no personal baseline, no session references) yields a
  matching unavailable label with the appropriate reason. Values are never
  invented to fill a gap (Requirement 24.3).

Inclusive boundary semantics are exactly as documented in ``thresholds.yaml``:

* ``fixed_bands`` (``boundary: inclusive_typical``):
  ``value < low_below`` -> ``labels[0]``; ``low_below <= value <= high_above`` ->
  ``labels[1]``; ``value > high_above`` -> ``labels[2]``. So e.g. speech rate 110
  and 170 -> typical, pause-time ratio 0.15 and 0.30 -> typical, relative pitch
  shift -3 and +3 -> typical.
* ``session_percentiles`` (``boundary: inclusive_typical``): ``value < P(low)`` ->
  low; ``P(low) <= value <= P(high)`` -> typical; ``value > P(high)`` -> high.
* ``binary`` (``boundary: greater_than``): ``value > threshold`` -> ``labels[1]``;
  otherwise ``labels[0]``. Used for ``nod_count > 0`` -> nod observed / absent.
* ``four_band`` (``boundary: inclusive_middle``, ``breaks: [b0, b1, b2]``):
  ``value == b0`` -> ``labels[0]``; ``b0 < value < b1`` -> ``labels[1]``;
  ``b1 <= value <= b2`` -> ``labels[2]``; ``value > b2`` -> ``labels[3]``.
* ``passthrough``: the feature's value (e.g. the interaction context) is carried
  through unchanged as the base label.

Session references input shape
------------------------------
Session-relative strategies read a :class:`SessionReferences` mapping: feature
name -> per-feature percentile dict (e.g. ``{"p25": 0.4, "p75": 0.8}``). The
percentile keys referenced by a strategy come from its ``low`` / ``high`` fields
(``p25`` / ``p75`` by default). When ``session_refs`` is ``None`` (the two-pass
session guard failed) or a required percentile is missing, the feature yields a
``status=INSUFFICIENT_REFERENCE_DATA`` label so the label engine can propagate
``insufficient_reference_data`` for the family (Requirement 13.3).
"""

from __future__ import annotations
from math import isfinite
from numbers import Real

from typing import Any, Callable, Mapping

from app.multimodal.config_loader import MethodologyConfig
from app.multimodal.schemas import (
    FamilyLabel,
    NonverbalBaseLabels,
    NonverbalProcessedFeatures,
    OutcomeStatus,
    ParaverbalBaseLabels,
    ParaverbalProcessedFeatures,
    UnavailableReason,
)

# A per-feature percentile reference: e.g. {"p25": 0.4, "p75": 0.8}.
FeatureReferences = Mapping[str, float]
# Session references: feature name -> its percentile reference.
SessionReferences = Mapping[str, FeatureReferences]


# ---------------------------------------------------------------------------
# Strategy context and result helpers
# ---------------------------------------------------------------------------


class _StrategyContext:
    """Everything a strategy needs to classify one feature.

    Bundled into a single object so the dispatch table entries share one uniform
    signature. ``value`` is the processed feature value (already ``None`` when the
    feature could not be derived), ``entry`` is the feature's threshold config
    block, and ``feature_refs`` is the per-feature session
    percentile dict (or ``None`` when session references are unavailable).
    """

    __slots__ = ("value", "entry", "baseline_available", "feature_refs")

    def __init__(
        self,
        *,
        value: Any,
        entry: Mapping[str, Any],
        baseline_available: bool,
        feature_refs: FeatureReferences | None,
    ) -> None:
        self.value = value
        self.entry = entry
        self.baseline_available = baseline_available
        self.feature_refs = feature_refs


def _ok(label: str, **evidence: Any) -> FamilyLabel:
    """Build an available base label carrying its raw label value.

    ``evidence`` records the inputs that produced the label (e.g. the numeric
    value and any percentile bounds) for downstream traceability.
    """
    return FamilyLabel(status=OutcomeStatus.OK, value=label, evidence=dict(evidence))


def _unavailable(reason: UnavailableReason) -> FamilyLabel:
    """Build an unavailable base label with an explanatory reason."""
    return FamilyLabel(status=OutcomeStatus.UNAVAILABLE, reason=reason)


def _insufficient_reference() -> FamilyLabel:
    """Build a base label marking missing/insufficient session references."""
    return FamilyLabel(
        status=OutcomeStatus.INSUFFICIENT_REFERENCE_DATA,
        reason=UnavailableReason.INSUFFICIENT_REFERENCE_DATA,
    )


# ---------------------------------------------------------------------------
# Strategy implementations
#
# Each strategy takes a _StrategyContext and returns exactly one FamilyLabel.
# None-valued features are handled centrally in _classify_feature before a
# strategy runs, so strategies here can assume a non-None value unless they
# specifically depend on an external prerequisite (baseline / references).
# ---------------------------------------------------------------------------


def _fixed_bands(ctx: _StrategyContext) -> FamilyLabel:
    """Three-band classification with boundaries inclusive to the typical band.

    ``value < low_below`` -> labels[0]; ``low_below <= value <= high_above`` ->
    labels[1]; ``value > high_above`` -> labels[2]. If either band edge is
    ``null`` in config the band is undecided and the feature is
    ``feature_unavailable``.
    """
    low_below = ctx.entry.get("low_below")
    high_above = ctx.entry.get("high_above")
    labels = ctx.entry.get("labels") or []
    if low_below is None or high_above is None or len(labels) < 3:
        return _unavailable(UnavailableReason.FEATURE_UNAVAILABLE)

    value = float(ctx.value)
    if value < low_below:
        chosen = labels[0]
    elif value > high_above:
        chosen = labels[2]
    else:  # low_below <= value <= high_above (boundaries inclusive to typical)
        chosen = labels[1]
    return _ok(chosen, value=value)


def _session_percentiles(ctx: _StrategyContext) -> FamilyLabel:
    """Session-relative classification against per-feature P(low)/P(high).

    ``value < P(low)`` -> labels[0]; ``P(low) <= value <= P(high)`` -> labels[1];
    ``value > P(high)`` -> labels[2] (boundaries inclusive to typical). When the
    session references are absent (guard failed) or a required percentile key is
    missing, the feature is ``insufficient_reference_data`` so the family can be
    short-circuited by the label engine (Requirement 13.3).
    """
    labels = ctx.entry.get("labels") or []
    low_key = ctx.entry.get("low", "p25")
    high_key = ctx.entry.get("high", "p75")
    if len(labels) < 3:
        return _unavailable(UnavailableReason.FEATURE_UNAVAILABLE)

    refs = ctx.feature_refs
    if refs is None or low_key not in refs or high_key not in refs:
        return _insufficient_reference()

    low_p = refs[low_key]
    high_p = refs[high_key]
    value = float(ctx.value)
    if value < low_p:
        chosen = labels[0]
    elif value > high_p:
        chosen = labels[2]
    else:  # P(low) <= value <= P(high)
        chosen = labels[1]
    return _ok(chosen, value=value, low=low_p, high=high_p)


def _binary(ctx: _StrategyContext) -> FamilyLabel:
    """Binary threshold classification: ``value > threshold`` -> labels[1].

    Used for nod presence (``nod_count > 0``). ``boundary: greater_than`` means
    the threshold itself is not "present"; a value strictly greater than the
    threshold selects ``labels[1]`` (observed), otherwise ``labels[0]`` (absent).
    """
    labels = ctx.entry.get("labels") or []
    threshold = ctx.entry.get("threshold", 0)
    if len(labels) < 2:
        return _unavailable(UnavailableReason.FEATURE_UNAVAILABLE)

    value = float(ctx.value)
    chosen = labels[1] if (value >= threshold if ctx.entry.get('boundary') == 'greater_or_equal' else value > threshold) else labels[0]
    return _ok(chosen, value=value)


def _pause_duration(ctx: _StrategyContext) -> FamilyLabel:
    value = float(ctx.value)
    labels = ctx.entry['labels']
    return _ok(labels[0] if value < ctx.entry['brief_below_ms'] else labels[1] if value < ctx.entry['long_from_ms'] else labels[2], value=value)


def _four_band(ctx: _StrategyContext) -> FamilyLabel:
    """Fixed four-band classification with ``inclusive_middle`` boundaries.

    For ascending breakpoints ``[b0, b1, b2]``: ``value == b0`` -> labels[0];
    ``b0 < value < b1`` -> labels[1]; ``b1 <= value <= b2`` -> labels[2];
    ``value > b2`` -> labels[3]. Any ``null`` breakpoint leaves the bands
    undecided and the feature is ``feature_unavailable``.
    """
    breaks = ctx.entry.get("breaks") or []
    labels = ctx.entry.get("labels") or []
    if len(breaks) < 3 or any(b is None for b in breaks) or len(labels) < 4:
        return _unavailable(UnavailableReason.FEATURE_UNAVAILABLE)

    b0, b1, b2 = breaks[0], breaks[1], breaks[2]
    value = float(ctx.value)
    if value == b0:
        chosen = labels[0]
    elif value < b1:  # b0 < value < b1 (value == b0 already handled)
        chosen = labels[1]
    elif value <= b2:  # b1 <= value <= b2 (breakpoints inclusive to middle band)
        chosen = labels[2]
    else:  # value > b2
        chosen = labels[3]
    return _ok(chosen, value=value)


def _passthrough(ctx: _StrategyContext) -> FamilyLabel:
    """Carry the feature value through unchanged as its base label.

    Used for the interaction context (``speaking`` / ``listening``), which is a
    contextual fact and not a thresholded measurement.
    """
    return _ok(str(ctx.value), value=ctx.value)


# Dispatch table: strategy name -> classifier. Resolving the strategy from this
# table (rather than per-feature branching) keeps the engine declarative.
_STRATEGIES: dict[str, Callable[[_StrategyContext], FamilyLabel]] = {
    "fixed_bands": _fixed_bands,
    "session_percentiles": _session_percentiles,
    "binary": _binary,
    "pause_duration": _pause_duration,
    "four_band": _four_band,
    "passthrough": _passthrough,
}

# ---------------------------------------------------------------------------
# Core classification of one feature
# ---------------------------------------------------------------------------


def _classify_feature(
    *,
    value: Any,
    entry: Mapping[str, Any],
    baseline_available: bool,
    feature_refs: FeatureReferences | None,
) -> FamilyLabel:
    """Classify a single processed feature into one base ``FamilyLabel``.

    Resolves the strategy declaratively from ``entry['strategy']``. A missing or
    ``None`` value yields ``feature_unavailable``; an unknown strategy name is a config
    error surfaced as ``processing_error`` so it is visible rather than silent.
    """
    strategy_name = entry.get("strategy") if isinstance(entry, Mapping) else None
    if strategy_name is None:
        return _unavailable(UnavailableReason.PROCESSING_ERROR)

    strategy = _STRATEGIES.get(strategy_name)
    if strategy is None:
        return _unavailable(UnavailableReason.PROCESSING_ERROR)

    if value is None:
        return _unavailable(UnavailableReason.FEATURE_UNAVAILABLE)
    if isinstance(value, Real) and not isfinite(value):
        return _unavailable(UnavailableReason.PROCESSING_ERROR)

    ctx = _StrategyContext(
        value=value,
        entry=entry,
        baseline_available=baseline_available,
        feature_refs=feature_refs,
    )
    return strategy(ctx)


def _classify_family(
    *,
    family_config: Mapping[str, Any],
    value_getter: Callable[[str], Any],
    baseline_available: bool,
    session_refs: SessionReferences | None,
    unavailable_reasons: Mapping[str, UnavailableReason] | None = None,
) -> dict[str, FamilyLabel]:
    """Classify every feature declared in one family's threshold config.

    ``value_getter`` maps a *config feature name* to the corresponding processed
    value. This indirection lets a config key differ from the processed-feature
    attribute (e.g. ``nod_present`` reads ``nod_count``; ``interaction_context``
    reads the processed ``context``) while keeping the engine declarative.
    """
    labels: dict[str, FamilyLabel] = {}
    for feature_name, entry in family_config.items():
        if not isinstance(entry, Mapping):
            labels[feature_name] = _unavailable(UnavailableReason.PROCESSING_ERROR)
            continue
        feature_refs = session_refs.get(feature_name) if session_refs else None
        value = value_getter(feature_name)
        reason_key = "nod_count" if feature_name == "nod_present" else feature_name
        if value is None and unavailable_reasons and reason_key in unavailable_reasons:
            labels[feature_name] = _unavailable(unavailable_reasons[reason_key])
            continue
        labels[feature_name] = _classify_feature(
            value=value,
            entry=entry,
            baseline_available=baseline_available,
            feature_refs=feature_refs,
        )
    return labels


# ---------------------------------------------------------------------------
# Config-name -> processed-feature value mappings
#
# Most config feature names match a ParaverbalProcessedFeatures /
# NonverbalProcessedFeatures attribute one-to-one. The few that differ are
# mapped explicitly so the rest fall through to attribute lookup.
# ---------------------------------------------------------------------------


def _nonverbal_value_getter(
    processed: NonverbalProcessedFeatures,
) -> Callable[[str], Any]:
    """Return a getter mapping a nonverbal config feature name to its value.

    ``nod_present`` is the binary view of ``nod_count`` (presence, not the raw
    count) and ``interaction_context`` is the passthrough of the processed
    ``context``; every other name maps directly to the same-named attribute.
    """
    explicit = {
        "nod_present": lambda: processed.nod_count,
        "interaction_context": lambda: processed.context,
    }

    def getter(feature_name: str) -> Any:
        if feature_name in explicit:
            return explicit[feature_name]()
        return getattr(processed, feature_name, None)

    return getter


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def compute_paraverbal_base_labels(
    processed: ParaverbalProcessedFeatures,
    config: MethodologyConfig,
    *,
    baseline_available: bool,
    session_refs: SessionReferences | None,
) -> ParaverbalBaseLabels:
    """Map paraverbal processed features to per-feature base labels.

    Produces base labels for the ``speech_timing``, ``prosodic_level``, and
    ``prosodic_variability`` families from the ``paraverbal`` section of
    ``thresholds.yaml``. Visual reference availability is tracked separately
    (relative pitch shift); ``session_refs`` supplies the per-feature P25/P75
    references for ``session_percentiles`` features, and is ``None`` when the
    session guard failed (yielding ``insufficient_reference_data`` labels).
    """
    paraverbal_config = config.thresholds.get("paraverbal", {})
    value_getter: Callable[[str], Any] = lambda name: getattr(processed, name, None)

    return ParaverbalBaseLabels(
        speech_timing=_classify_family(
            family_config=paraverbal_config.get("speech_timing", {}),
            value_getter=value_getter,
            baseline_available=baseline_available,
            session_refs=session_refs,
        ),
        prosodic_level=_classify_family(
            family_config=paraverbal_config.get("prosodic_level", {}),
            value_getter=value_getter,
            baseline_available=baseline_available,
            session_refs=session_refs,
        ),
        prosodic_variability=_classify_family(
            family_config=paraverbal_config.get("prosodic_variability", {}),
            value_getter=value_getter,
            baseline_available=baseline_available,
            session_refs=session_refs,
        ),
    )


def compute_nonverbal_base_labels(
    processed: NonverbalProcessedFeatures,
    config: MethodologyConfig,
    *,
    baseline_available: bool,
    session_refs: SessionReferences | None,
    unavailable_reasons: Mapping[str, UnavailableReason] | None = None,
) -> NonverbalBaseLabels:
    """Map nonverbal processed features to per-feature base labels.

    Produces base labels for the ``gaze_orientation``,
    ``head_nods``, and ``smile_activity`` families from the
    ``nonverbal`` section of ``thresholds.yaml``. ``session_refs`` supplies the
    per-feature P25/P75 references for the session-relative nod-rate and
    smile-activation features. ``baseline_available`` is accepted for a uniform
    signature with the paraverbal entry point; the current nonverbal strategies
    do not consume a personal baseline directly (the calibrated interaction
    center is applied earlier, during nonverbal preprocessing).
    """
    nonverbal_config = config.thresholds.get("nonverbal", {})
    value_getter = _nonverbal_value_getter(processed)

    return NonverbalBaseLabels(
        gaze_orientation=_classify_family(
            family_config=nonverbal_config.get("gaze_orientation", {}),
            value_getter=value_getter,
            baseline_available=baseline_available,
            session_refs=session_refs,
            unavailable_reasons=unavailable_reasons,
        ),
        head_nods=_classify_family(
            family_config=nonverbal_config.get("head_nods", {}),
            value_getter=value_getter,
            baseline_available=baseline_available,
            session_refs=session_refs,
            unavailable_reasons=unavailable_reasons,
        ),
        smile_activity=_classify_family(
            family_config=nonverbal_config.get("smile_activity", {}),
            value_getter=value_getter,
            baseline_available=baseline_available,
            session_refs=session_refs,
            unavailable_reasons=unavailable_reasons,
        ),
    )
