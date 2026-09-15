"""Declarative label engine for the multimodal pipeline (Requirement 12).

Maps per-feature Base_Labels to exactly one Integrated_Label per family using
``label_rules.yaml``. The engine is intentionally declarative and small: it
evaluates ordered rules against base labels, and never contains a mini
programming language. It references only base labels and configuration; it does
not touch OpenSMILE, Py-Feat, media, or any raw/signal internals
(Requirement 12.3).

Rule grammar (see ``config/label_rules.yaml``):

* Each family declares an ordered list of ``rules``. The first rule whose
  conditions all hold wins (ordered priority, Requirement 12.2).
* ``all: {slot: value}``  -> every slot's base label must equal ``value`` (AND).
* ``any: {slot: [v1, v2]}`` -> the slot's base label must be one of the listed
  values (OR / alternatives).
* A rule may combine ``all`` and ``any``; then both parts must hold.
* If no rule matches but the family's base labels are present, the ``fallback``
  value is used (Requirement 12.2).
* If the required base-label slots are missing or unavailable, the family
  yields an ``unavailable`` outcome with reason ``feature_unavailable``
  (Requirement 12.4, 14.2); a single outcome per family is always produced and
  never fabricated (Requirement 14.1).
* For ``session_relative`` families, if the session-relative base labels are
  ``insufficient_reference_data`` (propagated from the threshold engine when the
  minimum-turns guard failed), the family short-circuits to
  ``insufficient_reference_data`` before applying any rule (Requirement 13.3).

Slot -> feature mapping
-----------------------
``label_rules.yaml`` references *slot* names (e.g. ``global_rate``,
``pause_load``), while the threshold engine keys base labels by *feature* name
(the keys used in ``thresholds.yaml``, e.g. ``speech_rate_wpm``,
``pause_time_ratio``). This module owns the small, explicit mapping between the
two so a rule condition such as ``{pause_frequency: frecuencia_pausas_alta}`` is
checked against the base label produced for the ``pause_frequency_per_min``
feature. The mapping is defined in ``_SLOT_TO_FEATURE`` and documented there.
"""

from __future__ import annotations

from typing import Any

from .schemas import (
    FamilyLabel,
    NonverbalBaseLabels,
    NonverbalIntegratedLabels,
    OutcomeStatus,
    ParaverbalBaseLabels,
    ParaverbalIntegratedLabels,
    UnavailableReason,
)

# ---------------------------------------------------------------------------
# Slot -> feature mapping
#
# label_rules.yaml speaks in slot names; the threshold engine keys base labels
# by the feature names used in thresholds.yaml. This explicit table bridges the
# two. It is deliberately a plain data table (no logic) so the mapping is
# auditable and matches the slot names documented in label_rules.yaml against
# the feature keys documented in thresholds.yaml.
# ---------------------------------------------------------------------------

_SLOT_TO_FEATURE: dict[str, dict[str, str]] = {
    # Paraverbal families
    "temporal": {
        "global_rate": "speech_rate_wpm",
        "articulation": "articulation_rate_wpm",
        "pause_load": "pause_time_ratio",
        "pause_duration": "median_pause_duration_ms",
        "pause_frequency": "pause_frequency_per_min",
    },
    "prosodic_level": {
        "pitch_level": "relative_pitch_shift_st",
        "loudness_level": "median_loudness",
    },
    "prosodic_modulation": {
        "pitch_variation": "f0_p20_p80_range_semitones",
        "loudness_variation": "loudness_p20_p80_range",
    },
    # Nonverbal families
    "visual_orientation": {
        "alignment": "visual_alignment_ratio",
        "dwell": "median_visual_alignment_dwell_ms",
    },
    "head_gestural_feedback": {
        "nod_present": "nod_present",
        "nod_rate": "nod_rate_min",
        "context": "interaction_context",
    },
    "facial_expressivity": {
        "smile_activity": "smile_activity_ratio",
        "smile_activation": "mean_smile_activation",
    },
}

_PARAVERBAL_FAMILIES = ("temporal", "prosodic_level", "prosodic_modulation")
_NONVERBAL_FAMILIES = (
    "visual_orientation",
    "head_gestural_feedback",
    "facial_expressivity",
)


# ---------------------------------------------------------------------------
# Core rule evaluation (declarative, per family)
# ---------------------------------------------------------------------------


def _resolve_slot_value(
    family: str,
    slot: str,
    base_labels: dict[str, FamilyLabel],
) -> str | None:
    """Return the OK base-label value for ``slot`` in ``family``, else ``None``.

    Maps the rule ``slot`` to its feature key and reads the corresponding base
    label. A slot resolves to a usable value only when the base label exists and
    has status ``OK`` with a non-null value; a missing or unavailable base label
    resolves to ``None`` so any rule condition referencing it fails.
    """

    feature = _SLOT_TO_FEATURE.get(family, {}).get(slot, slot)
    label = base_labels.get(feature)
    if label is None:
        return None
    if label.status != OutcomeStatus.OK:
        return None
    return label.value


def _rule_matches(
    family: str,
    rule: dict[str, Any],
    base_labels: dict[str, FamilyLabel],
    evidence: dict[str, str],
) -> bool:
    """Return True if every ``all`` (AND) and ``any`` (OR) condition holds.

    Records the slot -> matched base-label value into ``evidence`` only when the
    whole rule matches (the caller passes a scratch dict and copies it on a win).
    """

    matched: dict[str, str] = {}

    all_conditions: dict[str, str] = rule.get("all") or {}
    for slot, expected in all_conditions.items():
        actual = _resolve_slot_value(family, slot, base_labels)
        if actual != expected:
            return False
        matched[slot] = actual

    any_conditions: dict[str, list[str]] = rule.get("any") or {}
    for slot, options in any_conditions.items():
        actual = _resolve_slot_value(family, slot, base_labels)
        if actual is None or actual not in options:
            return False
        matched[slot] = actual

    evidence.clear()
    evidence.update(matched)
    return True


def _referenced_slots(rules: list[dict[str, Any]]) -> set[str]:
    """Collect every slot referenced by any rule's ``all``/``any`` conditions."""

    slots: set[str] = set()
    for rule in rules:
        slots.update((rule.get("all") or {}).keys())
        slots.update((rule.get("any") or {}).keys())
    return slots


def _has_any_usable_slot(
    family: str,
    rules: list[dict[str, Any]],
    base_labels: dict[str, FamilyLabel],
) -> bool:
    """Return True if at least one slot referenced by the rules is usable.

    "Usable" means the mapped base label exists with status ``OK``. When no
    referenced slot is usable, the family's base labels are insufficient to
    select any integrated label and the family is treated as unavailable rather
    than forced onto the fallback.
    """

    for slot in _referenced_slots(rules):
        if _resolve_slot_value(family, slot, base_labels) is not None:
            return True
    return False


def _is_insufficient_reference(base_labels: dict[str, FamilyLabel]) -> bool:
    """Return True if any base label signals ``insufficient_reference_data``.

    Session-relative families propagate this status from the threshold engine
    when the minimum-turns guard failed; a single such slot is enough to make
    the whole family insufficient (Requirement 13.3).
    """

    return any(
        label.status == OutcomeStatus.INSUFFICIENT_REFERENCE_DATA
        for label in base_labels.values()
    )


def integrate_family(
    family: str,
    base_labels: dict[str, FamilyLabel],
    family_config: dict[str, Any],
) -> FamilyLabel:
    """Resolve exactly one integrated ``FamilyLabel`` for a single family.

    Order of decision:

    1. Session-relative propagation: if the family is ``session_relative`` and
       any of its base labels is ``insufficient_reference_data``, short-circuit
       to that status before applying rules (Requirement 13.3).
    2. Sufficiency: if no referenced slot has a usable (OK) base label, the
       family is ``unavailable`` / ``feature_unavailable`` (Requirement 12.4,
       14.2).
    3. Ordered rules: return the first rule whose conditions all hold, recording
       the driving base labels in ``evidence`` (Requirement 12.2).
    4. Fallback: if base labels are present but no rule matches, use the
       family's ``fallback`` value (Requirement 12.2).
    """

    rules: list[dict[str, Any]] = family_config.get("rules") or []
    session_relative: bool = bool(family_config.get("session_relative", False))

    # 1. Session-relative insufficient-reference propagation (before rules).
    if session_relative and _is_insufficient_reference(base_labels):
        return FamilyLabel(
            status=OutcomeStatus.INSUFFICIENT_REFERENCE_DATA,
            reason=UnavailableReason.INSUFFICIENT_REFERENCE_DATA,
            evidence={
                slot: label.status.value
                for slot, label in base_labels.items()
                if label.status == OutcomeStatus.INSUFFICIENT_REFERENCE_DATA
            },
        )

    # 2. Sufficiency guard: at least one referenced slot must be usable.
    if not _has_any_usable_slot(family, rules, base_labels):
        return FamilyLabel(
            status=OutcomeStatus.UNAVAILABLE,
            reason=UnavailableReason.FEATURE_UNAVAILABLE,
            evidence={},
        )

    # 3. Ordered rule evaluation: first match wins (priority).
    for rule in rules:
        evidence: dict[str, str] = {}
        if _rule_matches(family, rule, base_labels, evidence):
            return FamilyLabel(
                status=OutcomeStatus.OK,
                value=rule.get("value"),
                evidence=dict(evidence),
            )

    # 4. Fallback: base labels are present but did not match any rule.
    fallback = family_config.get("fallback")
    if fallback is not None:
        return FamilyLabel(
            status=OutcomeStatus.OK,
            value=fallback,
            evidence={
                slot: value
                for slot in _referenced_slots(rules)
                if (value := _resolve_slot_value(family, slot, base_labels))
                is not None
            },
        )

    # No fallback declared and nothing matched -> unavailable with reason.
    return FamilyLabel(
        status=OutcomeStatus.UNAVAILABLE,
        reason=UnavailableReason.FEATURE_UNAVAILABLE,
        evidence={},
    )


def _families_config(config: Any) -> dict[str, Any]:
    """Return the ``families`` mapping from the label-rules config.

    Accepts either a ``MethodologyConfig`` (reads ``config.label_rules``) or a
    already-extracted label-rules mapping, so callers can pass whichever they
    hold without this module importing the config loader.
    """

    label_rules = getattr(config, "label_rules", config)
    families = label_rules.get("families")
    if not isinstance(families, dict):
        raise ValueError("label_rules config has no 'families' mapping")
    return families


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def integrate_paraverbal_labels(
    base_labels: ParaverbalBaseLabels,
    config: Any,
) -> ParaverbalIntegratedLabels:
    """Integrate the three paraverbal families into one label each.

    Args:
        base_labels: Per-feature paraverbal base labels grouped by family.
        config: A ``MethodologyConfig`` or the parsed ``label_rules`` mapping.

    Returns:
        Exactly one ``FamilyLabel`` per paraverbal family (Requirement 8.4-8.6).
    """

    families = _families_config(config)
    per_family = {
        name: integrate_family(
            name,
            getattr(base_labels, name),
            families.get(name, {}),
        )
        for name in _PARAVERBAL_FAMILIES
    }
    return ParaverbalIntegratedLabels(**per_family)


def integrate_nonverbal_labels(
    base_labels: NonverbalBaseLabels,
    config: Any,
) -> NonverbalIntegratedLabels:
    """Integrate the three nonverbal families into one label each.

    Args:
        base_labels: Per-feature nonverbal base labels grouped by family.
        config: A ``MethodologyConfig`` or the parsed ``label_rules`` mapping.

    Returns:
        Exactly one ``FamilyLabel`` per nonverbal family (Requirement 10.5-10.7).
    """

    families = _families_config(config)
    per_family = {
        name: integrate_family(
            name,
            getattr(base_labels, name),
            families.get(name, {}),
        )
        for name in _NONVERBAL_FAMILIES
    }
    return NonverbalIntegratedLabels(**per_family)
