"""Tests for the declarative label engine (Requirements 28.5, 12.1, 12.2, 12.4, 13.3, 14.2).

These tests exercise the public API of ``app.multimodal.label_engine``:

* ``integrate_paraverbal_labels(base_labels, config)`` and
* ``integrate_nonverbal_labels(base_labels, config)``.

The real bundled methodology config is loaded via ``load_methodology_config``
so the rule set under test is exactly the one that ships in
``config/label_rules.yaml``. Base labels are built directly as per-feature
``FamilyLabel`` objects keyed by the *feature* names used in
``thresholds.yaml`` (not the *slot* names used inside ``label_rules.yaml``); the
mapping between the two lives in ``label_engine._SLOT_TO_FEATURE``. All base
label values are the verbatim research strings from the YAML so the assertions
are faithful to the shipped configuration.

The engine is deterministic: given the same base labels and config, it always
produces the same integrated label per family. Every case is therefore a
straightforward input -> output assertion with no randomness.

Coverage across the six families:

* AND rule (``all``): a temporal rule whose conditions all hold.
* OR / alternatives (``any``): a rule that matches one of several options.
* Ordered priority: an earlier-listed rule wins over a later one.
* Explicit fallback: base labels present but matching no rule.
* Unavailable: required slots unavailable -> UNAVAILABLE / FEATURE_UNAVAILABLE.
* Session-relative ``insufficient_reference_data`` propagation.
* Evidence: the driving slots are recorded on a match.
"""

from __future__ import annotations

import pytest

from app.multimodal.config_loader import load_methodology_config
from app.multimodal.label_engine import (
    integrate_nonverbal_labels,
    integrate_paraverbal_labels,
)
from app.multimodal.schemas import (
    FamilyLabel,
    NonverbalBaseLabels,
    OutcomeStatus,
    ParaverbalBaseLabels,
    UnavailableReason,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def config():
    """Load the real bundled methodology config once for the module."""

    return load_methodology_config()


def ok(value: str) -> FamilyLabel:
    """Build an OK per-feature base label carrying ``value``."""

    return FamilyLabel(status=OutcomeStatus.OK, value=value)


def unavailable() -> FamilyLabel:
    """Build an unavailable per-feature base label (feature_unavailable)."""

    return FamilyLabel(
        status=OutcomeStatus.UNAVAILABLE,
        reason=UnavailableReason.FEATURE_UNAVAILABLE,
    )


def insufficient_reference() -> FamilyLabel:
    """Build a session-relative insufficient_reference_data base label."""

    return FamilyLabel(
        status=OutcomeStatus.INSUFFICIENT_REFERENCE_DATA,
        reason=UnavailableReason.INSUFFICIENT_REFERENCE_DATA,
    )


# Feature keys per family (from thresholds.yaml / _SLOT_TO_FEATURE), so the
# tests build base labels keyed exactly as the engine reads them.
#
# temporal:            speech_rate_wpm, articulation_rate_wpm,
#                      pause_time_ratio, median_pause_duration_ms,
#                      pause_frequency_per_min
# prosodic_level:      relative_pitch_shift_st, median_loudness
# prosodic_modulation: f0_p20_p80_range_semitones, loudness_p20_p80_range
# visual_orientation:  visual_alignment_ratio, median_visual_alignment_dwell_ms
# head_gestural_feedback: nod_present, nod_rate_min, interaction_context
# facial_expressivity: smile_activity_ratio, mean_smile_activation


def paraverbal(
    *,
    temporal: dict[str, FamilyLabel] | None = None,
    prosodic_level: dict[str, FamilyLabel] | None = None,
    prosodic_modulation: dict[str, FamilyLabel] | None = None,
) -> ParaverbalBaseLabels:
    """Build ParaverbalBaseLabels with empty families defaulted."""

    return ParaverbalBaseLabels(
        temporal=temporal or {},
        prosodic_level=prosodic_level or {},
        prosodic_modulation=prosodic_modulation or {},
    )


def nonverbal(
    *,
    visual_orientation: dict[str, FamilyLabel] | None = None,
    head_gestural_feedback: dict[str, FamilyLabel] | None = None,
    facial_expressivity: dict[str, FamilyLabel] | None = None,
) -> NonverbalBaseLabels:
    """Build NonverbalBaseLabels with empty families defaulted."""

    return NonverbalBaseLabels(
        visual_orientation=visual_orientation or {},
        head_gestural_feedback=head_gestural_feedback or {},
        facial_expressivity=facial_expressivity or {},
    )


# ===========================================================================
# PARAVERBAL — temporal (fixed bands, not session-relative)
# ===========================================================================


def test_temporal_and_rule_fragmentado(config) -> None:
    """AND rule: high frequency + short pauses -> fragmented_by_brief_pauses.

    Covers the ``all`` (AND) grammar: the first temporal rule requires both
    ``pause_frequency`` and ``pause_duration`` to hold (Requirement 12.1).
    """

    base = paraverbal(
        temporal={
            "pause_frequency_per_min": ok("pause_frequency_high"),
            "median_pause_duration_ms": ok("pause_duration_brief"),
        }
    )

    result = integrate_paraverbal_labels(base, config)

    assert result.temporal.status == OutcomeStatus.OK
    assert result.temporal.value == "fragmented_by_brief_pauses"
    # Evidence records the driving slots (slot names, not feature keys).
    assert result.temporal.evidence["pause_frequency"] == "pause_frequency_high"
    assert (
        result.temporal.evidence["pause_duration"]
        == "pause_duration_brief"
    )


def test_temporal_or_rule_intermitente(config) -> None:
    """OR/alternatives: long pauses + (pause_load high OR typical).

    Covers the ``any`` grammar on ``pause_load``: the rule matches when the
    slot value is one of the two listed options (Requirement 12.1).
    """

    # any: {pause_load: [pause_load_high, pause_load_typical]} -> pick typical.
    base = paraverbal(
        temporal={
            "median_pause_duration_ms": ok("pause_duration_long"),
            "pause_time_ratio": ok("pause_load_typical"),
        }
    )

    result = integrate_paraverbal_labels(base, config)

    assert result.temporal.status == OutcomeStatus.OK
    assert result.temporal.value == "intermittent_by_long_pauses"
    assert result.temporal.evidence["pause_load"] == "pause_load_typical"


def test_temporal_ordered_priority_first_match_wins(config) -> None:
    """Ordered priority: an earlier rule wins over a lower one that also holds.

    ``fragmented_by_brief_pauses`` (rule 1) and ``high_pause_load``
    (rule 8) can both hold for the same base labels; the earlier one must win
    (Requirement 12.2).
    """

    # Satisfies rule 1 (high freq + short pauses) AND rule 8 (carga alta).
    base = paraverbal(
        temporal={
            "pause_frequency_per_min": ok("pause_frequency_high"),
            "median_pause_duration_ms": ok("pause_duration_brief"),
            "pause_time_ratio": ok("pause_load_high"),
        }
    )

    result = integrate_paraverbal_labels(base, config)

    # Earlier-listed rule 1 wins over rule 8.
    assert result.temporal.value == "fragmented_by_brief_pauses"


def test_temporal_typical_pattern(config) -> None:
    """A typical temporal pattern resolves to typical_temporal_pattern."""

    base = paraverbal(
        temporal={
            "speech_rate_wpm": ok("speech_rate_typical"),
            "articulation_rate_wpm": ok("articulation_rate_typical"),
            "pause_time_ratio": ok("pause_load_typical"),
        }
    )

    result = integrate_paraverbal_labels(base, config)

    assert result.temporal.value == "typical_temporal_pattern"


def test_temporal_fallback_when_no_rule_matches(config) -> None:
    """Explicit fallback: present base labels matching no rule -> fallback.

    A lone ``speech_rate_high`` (with no pause_load) matches none of the
    ordered rules, so the family fallback value is used (Requirement 12.2).
    """

    base = paraverbal(temporal={"speech_rate_wpm": ok("speech_rate_high")})

    result = integrate_paraverbal_labels(base, config)

    assert result.temporal.status == OutcomeStatus.OK
    assert result.temporal.value == "mixed_temporal_pattern_unclassified"


def test_temporal_unavailable_when_all_slots_unavailable(config) -> None:
    """Unavailable: every temporal slot unavailable -> FEATURE_UNAVAILABLE.

    When no referenced slot is usable, the family is UNAVAILABLE with reason
    FEATURE_UNAVAILABLE rather than being forced onto the fallback
    (Requirement 12.4, 14.2).
    """

    base = paraverbal(
        temporal={
            "speech_rate_wpm": unavailable(),
            "articulation_rate_wpm": unavailable(),
            "pause_time_ratio": unavailable(),
        }
    )

    result = integrate_paraverbal_labels(base, config)

    assert result.temporal.status == OutcomeStatus.UNAVAILABLE
    assert result.temporal.reason == UnavailableReason.FEATURE_UNAVAILABLE
    assert result.temporal.value is None


# ===========================================================================
# PARAVERBAL — prosodic_level (session-relative)
# ===========================================================================


def test_prosodic_level_and_rule_elevado(config) -> None:
    """AND rule: high pitch + high loudness -> elevated_prosodic_level."""

    base = paraverbal(
        prosodic_level={
            "relative_pitch_shift_st": ok("relative_pitch_high"),
            "median_loudness": ok("loudness_high"),
        }
    )

    result = integrate_paraverbal_labels(base, config)

    assert result.prosodic_level.value == "elevated_prosodic_level"
    assert result.prosodic_level.evidence["pitch_level"] == "relative_pitch_high"
    assert result.prosodic_level.evidence["loudness_level"] == "loudness_high"


def test_prosodic_level_typical(config) -> None:
    """Typical pitch + typical loudness -> typical_prosodic_level."""

    base = paraverbal(
        prosodic_level={
            "relative_pitch_shift_st": ok("relative_pitch_typical"),
            "median_loudness": ok("loudness_typical"),
        }
    )

    result = integrate_paraverbal_labels(base, config)

    assert result.prosodic_level.value == "typical_prosodic_level"


def test_prosodic_level_insufficient_reference_propagates(config) -> None:
    """Session-relative: an insufficient_reference base label propagates.

    ``prosodic_level`` is session_relative; a single session-relative base
    label with INSUFFICIENT_REFERENCE_DATA short-circuits the whole family to
    that status before any rule runs (Requirement 13.3).
    """

    base = paraverbal(
        prosodic_level={
            "relative_pitch_shift_st": ok("relative_pitch_high"),
            "median_loudness": insufficient_reference(),
        }
    )

    result = integrate_paraverbal_labels(base, config)

    assert (
        result.prosodic_level.status == OutcomeStatus.INSUFFICIENT_REFERENCE_DATA
    )
    assert (
        result.prosodic_level.reason
        == UnavailableReason.INSUFFICIENT_REFERENCE_DATA
    )
    assert result.prosodic_level.value is None


# ===========================================================================
# PARAVERBAL — prosodic_modulation (session-relative)
# ===========================================================================


def test_prosodic_modulation_and_rule_expresiva(config) -> None:
    """AND rule: variable intonation + high loudness variation -> expresiva."""

    base = paraverbal(
        prosodic_modulation={
            "f0_p20_p80_range_semitones": ok("intonation_variable"),
            "loudness_p20_p80_range": ok("loudness_variability_high"),
        }
    )

    result = integrate_paraverbal_labels(base, config)

    assert result.prosodic_modulation.value == "expressive_modulation"


def test_prosodic_modulation_single_slot_rule(config) -> None:
    """A lone high loudness-variation label matches the single-slot rule.

    With only ``loudness_p20_p80_range`` = ``loudness_variability_high`` present
    (pitch missing), the paired ``expressive_modulation`` rule cannot hold, so
    the single-slot rule ``marked_loudness_variability`` fires instead.
    """

    base = paraverbal(
        prosodic_modulation={
            "loudness_p20_p80_range": ok("loudness_variability_high"),
        }
    )

    result = integrate_paraverbal_labels(base, config)

    assert result.prosodic_modulation.value == "marked_loudness_variability"


def test_prosodic_modulation_fallback(config) -> None:
    """Explicit fallback: a present-but-unmatched base label -> fallback.

    A lone typical pitch (``intonation_typical``) with no loudness slot matches
    no modulation rule: every rule referencing pitch alone needs
    ``intonation_variable`` or ``intonation_monotone``, and the typical rule
    needs both slots. The family fallback ``mixed_modulation_unclassified``
    therefore applies (Requirement 12.2). The pitch slot is usable, so the
    sufficiency guard passes and the fallback is reached (not UNAVAILABLE).
    """

    base = paraverbal(
        prosodic_modulation={
            "f0_p20_p80_range_semitones": ok("intonation_typical"),
        }
    )

    result = integrate_paraverbal_labels(base, config)

    assert result.prosodic_modulation.value == "mixed_modulation_unclassified"


def test_prosodic_modulation_insufficient_reference_propagates(config) -> None:
    """Session-relative insufficient_reference propagation for modulation."""

    base = paraverbal(
        prosodic_modulation={
            "f0_p20_p80_range_semitones": insufficient_reference(),
            "loudness_p20_p80_range": insufficient_reference(),
        }
    )

    result = integrate_paraverbal_labels(base, config)

    assert (
        result.prosodic_modulation.status
        == OutcomeStatus.INSUFFICIENT_REFERENCE_DATA
    )


# ===========================================================================
# NONVERBAL — visual_orientation (fixed bands, not session-relative)
# ===========================================================================


def test_visual_orientation_and_rule_sostenida(config) -> None:
    """AND rule: high alignment + long dwell -> sustained_visual_orientation."""

    base = nonverbal(
        visual_orientation={
            "visual_alignment_ratio": ok("visual_alignment_high"),
            "median_visual_alignment_dwell_ms": ok("visual_dwell_sustained"),
        }
    )

    result = integrate_nonverbal_labels(base, config)

    assert result.visual_orientation.value == "sustained_visual_orientation"
    assert (
        result.visual_orientation.evidence["alignment"] == "visual_alignment_high"
    )
    assert (
        result.visual_orientation.evidence["dwell"]
        == "visual_dwell_sustained"
    )


def test_visual_orientation_or_rule_fragmentada(config) -> None:
    """OR/alternatives: short dwell + (typical OR high alignment) -> fragmentada.

    Covers ``any`` on ``alignment`` for the third visual-orientation rule.
    """

    base = nonverbal(
        visual_orientation={
            "median_visual_alignment_dwell_ms": ok("visual_dwell_brief"),
            "visual_alignment_ratio": ok("visual_alignment_mid"),
        }
    )

    result = integrate_nonverbal_labels(base, config)

    assert result.visual_orientation.value == "fragmented_visual_orientation"


def test_visual_orientation_ordered_priority(config) -> None:
    """Ordered priority: low-alignment rule wins over the fragmented rule.

    With low alignment + short dwell, rule 2 (scarce_visual_orientation) is
    listed before rule 3 (fragmented_visual_orientation). Rule 3's ``any``
    would not match low alignment, but rule 2 fires first regardless
    (Requirement 12.2).
    """

    base = nonverbal(
        visual_orientation={
            "visual_alignment_ratio": ok("visual_alignment_low"),
            "median_visual_alignment_dwell_ms": ok("visual_dwell_brief"),
        }
    )

    result = integrate_nonverbal_labels(base, config)

    assert result.visual_orientation.value == "scarce_visual_orientation"


def test_visual_orientation_fallback(config) -> None:
    """Fallback: high alignment with typical dwell matches no rule -> fallback."""

    base = nonverbal(
        visual_orientation={
            "visual_alignment_ratio": ok("visual_alignment_high"),
            "median_visual_alignment_dwell_ms": ok("visual_dwell_typical"),
        }
    )

    result = integrate_nonverbal_labels(base, config)

    assert (
        result.visual_orientation.value == "mixed_visual_orientation_unclassified"
    )


def test_visual_orientation_unavailable(config) -> None:
    """Unavailable: both visual-orientation slots unavailable -> FEATURE_UNAVAILABLE."""

    base = nonverbal(
        visual_orientation={
            "visual_alignment_ratio": unavailable(),
            "median_visual_alignment_dwell_ms": unavailable(),
        }
    )

    result = integrate_nonverbal_labels(base, config)

    assert result.visual_orientation.status == OutcomeStatus.UNAVAILABLE
    assert (
        result.visual_orientation.reason == UnavailableReason.FEATURE_UNAVAILABLE
    )


# ===========================================================================
# NONVERBAL — head_gestural_feedback (session-relative)
# ===========================================================================


def test_head_feedback_no_nod(config) -> None:
    """AND rule: nod absent -> no_nodding (first rule)."""

    base = nonverbal(
        head_gestural_feedback={"nod_present": ok("nod_absent")}
    )

    result = integrate_nonverbal_labels(base, config)

    assert result.head_gestural_feedback.value == "no_nodding"
    assert result.head_gestural_feedback.evidence["nod_present"] == "nod_absent"


def test_head_feedback_frequent_nods(config) -> None:
    """AND rule: nod observed + high nod rate -> frequent_nodding."""

    base = nonverbal(
        head_gestural_feedback={
            "nod_present": ok("nod_observed"),
            "nod_rate_min": ok("nod_rate_high"),
        }
    )

    result = integrate_nonverbal_labels(base, config)

    assert result.head_gestural_feedback.value == "frequent_nodding"


def test_head_feedback_ordered_priority_over_present(config) -> None:
    """Ordered priority: high-rate rule wins over the bare 'present' rule.

    ``frequent_nodding`` (rule 2) is listed before ``nodding_present``
    (rule 4); with nod observed + high rate both could hold, the earlier wins
    (Requirement 12.2).
    """

    base = nonverbal(
        head_gestural_feedback={
            "nod_present": ok("nod_observed"),
            "nod_rate_min": ok("nod_rate_high"),
        }
    )

    result = integrate_nonverbal_labels(base, config)

    assert result.head_gestural_feedback.value == "frequent_nodding"


def test_head_feedback_present_fallback_rule(config) -> None:
    """Nod observed with a typical rate falls to the bare 'present' rule."""

    base = nonverbal(
        head_gestural_feedback={
            "nod_present": ok("nod_observed"),
            "nod_rate_min": ok("nod_rate_typical"),
        }
    )

    result = integrate_nonverbal_labels(base, config)

    assert result.head_gestural_feedback.value == "nodding_present"


def test_head_feedback_insufficient_reference_propagates(config) -> None:
    """Session-relative: insufficient nod-rate reference propagates.

    ``head_gestural_feedback`` is session_relative, so an
    INSUFFICIENT_REFERENCE_DATA on ``nod_rate_min`` short-circuits the family
    even though ``nod_present`` is available (Requirement 13.3).
    """

    base = nonverbal(
        head_gestural_feedback={
            "nod_present": ok("nod_observed"),
            "nod_rate_min": insufficient_reference(),
        }
    )

    result = integrate_nonverbal_labels(base, config)

    assert (
        result.head_gestural_feedback.status
        == OutcomeStatus.INSUFFICIENT_REFERENCE_DATA
    )


# ===========================================================================
# NONVERBAL — facial_expressivity (session-relative, four-band smile)
# ===========================================================================


def test_facial_expressivity_absent(config) -> None:
    """AND rule: absent smile activity -> absent_facial_expressivity."""

    base = nonverbal(
        facial_expressivity={"smile_activity_ratio": ok("smile_activity_absent")}
    )

    result = integrate_nonverbal_labels(base, config)

    assert result.facial_expressivity.value == "absent_facial_expressivity"


def test_facial_expressivity_marked_and_rule(config) -> None:
    """AND rule: frequent activity + high activation -> marked_facial_expressivity."""

    base = nonverbal(
        facial_expressivity={
            "smile_activity_ratio": ok("smile_activity_frequent"),
            "mean_smile_activation": ok("smile_activation_marked"),
        }
    )

    result = integrate_nonverbal_labels(base, config)

    assert result.facial_expressivity.value == "marked_facial_expressivity"


def test_facial_expressivity_ordered_priority(config) -> None:
    """Ordered priority: 'marcada' (rule 2) wins over 'frecuente' (rule 3).

    Frequent activity + high activation satisfies both rule 2 and rule 3; the
    earlier-listed rule 2 wins (Requirement 12.2).
    """

    base = nonverbal(
        facial_expressivity={
            "smile_activity_ratio": ok("smile_activity_frequent"),
            "mean_smile_activation": ok("smile_activation_marked"),
        }
    )

    result = integrate_nonverbal_labels(base, config)

    assert result.facial_expressivity.value == "marked_facial_expressivity"


def test_facial_expressivity_moderate(config) -> None:
    """Moderate smile activity -> moderate_facial_expressivity."""

    base = nonverbal(
        facial_expressivity={"smile_activity_ratio": ok("smile_activity_moderate")}
    )

    result = integrate_nonverbal_labels(base, config)

    assert result.facial_expressivity.value == "moderate_facial_expressivity"


def test_facial_expressivity_insufficient_reference_propagates(config) -> None:
    """Session-relative: insufficient smile-activation reference propagates."""

    base = nonverbal(
        facial_expressivity={
            "smile_activity_ratio": ok("smile_activity_frequent"),
            "mean_smile_activation": insufficient_reference(),
        }
    )

    result = integrate_nonverbal_labels(base, config)

    assert (
        result.facial_expressivity.status
        == OutcomeStatus.INSUFFICIENT_REFERENCE_DATA
    )
