"""Tests for the declarative threshold engine (Requirements 28.4, 11.2, 11.3, 11.4).

These tests drive the public entry points of ``app.multimodal.threshold_engine``:

* ``compute_paraverbal_base_labels`` and ``compute_nonverbal_base_labels``

against the *real* bundled methodology configuration loaded via
``load_methodology_config()``. Processed-feature contracts
(``ParaverbalProcessedFeatures`` / ``NonverbalProcessedFeatures``) are built
directly, so the tests exercise only the threshold stage.

Every asserted base-label string is read live from ``thresholds.yaml`` through
the loaded config (helper ``_labels_for``) rather than hard-coded, so the tests
stay consistent with the config file and fail loudly if the label vocabulary
changes. All cases are deterministic: no randomness, no I/O beyond the one-time
config load.

Boundary focus (the reason this suite exists): the ``inclusive_typical``
strategies place both band edges inside the typical band, so e.g. speech rate
110 and 170 are both ``typical`` while 109.999 is ``low`` and 170.001 is
``high``. The four-band smile strategy is ``inclusive_middle`` and the binary
nod strategy is ``greater_than``.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.multimodal.config_loader import MethodologyConfig, load_methodology_config
from app.multimodal.schemas import (
    NonverbalProcessedFeatures,
    OutcomeStatus,
    ParaverbalProcessedFeatures,
    UnavailableReason,
)
from app.multimodal.threshold_engine import (
    compute_nonverbal_base_labels,
    compute_paraverbal_base_labels,
)


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def config() -> MethodologyConfig:
    """Load the real bundled methodology config once for the whole module."""
    return load_methodology_config()


def _entry(config: MethodologyConfig, modality: str, family: str, feature: str) -> dict:
    """Return the raw threshold config block for one feature."""
    return config.thresholds[modality][family][feature]


def _labels_for(
    config: MethodologyConfig, modality: str, family: str, feature: str
) -> list[str]:
    """Read the ordered label strings declared for a feature in thresholds.yaml.

    Asserting against these live values keeps the tests coupled to the config
    file rather than to a duplicated copy of the label vocabulary.
    """
    return _entry(config, modality, family, feature)["labels"]


def _para(**overrides: Any) -> ParaverbalProcessedFeatures:
    """Build ParaverbalProcessedFeatures with only the given fields set."""
    return ParaverbalProcessedFeatures(**overrides)


def _nonverbal(**overrides: Any) -> NonverbalProcessedFeatures:
    """Build NonverbalProcessedFeatures with only the given fields set."""
    return NonverbalProcessedFeatures(**overrides)


# ---------------------------------------------------------------------------
# fixed_bands: inclusive-to-typical boundaries across every paraverbal temporal
# and prosodic-modulation feature and the nonverbal visual-orientation features.
#
# Each case is (low_edge, high_edge): value < low_edge -> labels[0],
# low_edge and high_edge inclusive -> labels[1], value > high_edge -> labels[2].
# ---------------------------------------------------------------------------

# (modality, family, feature, low_edge, high_edge)
_FIXED_BAND_FEATURES = [
    ("paraverbal", "temporal", "speech_rate_wpm", 110, 170),
    ("paraverbal", "temporal", "articulation_rate_wpm", 130, 210),
    ("paraverbal", "temporal", "median_pause_duration_ms", 500, 1000),
    ("paraverbal", "temporal", "pause_frequency_per_min", 12, 24),
    ("paraverbal", "temporal", "pause_time_ratio", 0.15, 0.30),
    ("paraverbal", "prosodic_modulation", "f0_p20_p80_range_semitones", 4, 8),
    ("nonverbal", "visual_orientation", "visual_alignment_ratio", 0.30, 0.65),
    ("nonverbal", "visual_orientation", "median_visual_alignment_dwell_ms", 500, 1500),
]


def _classify_single(
    config: MethodologyConfig, modality: str, family: str, feature: str, value: Any
):
    """Run the appropriate engine entry point and return the feature's label."""
    if modality == "paraverbal":
        result = compute_paraverbal_base_labels(
            _para(**{feature: value}),
            config,
            baseline_available=True,
            session_refs=None,
        )
        return getattr(result, family)[feature]
    result = compute_nonverbal_base_labels(
        _nonverbal(**{feature: value}),
        config,
        baseline_available=True,
        session_refs=None,
    )
    return getattr(result, family)[feature]


@pytest.mark.parametrize(
    "modality,family,feature,low_edge,high_edge", _FIXED_BAND_FEATURES
)
def test_fixed_bands_lower_boundary_is_typical(
    config, modality, family, feature, low_edge, high_edge
):
    """The lower band edge itself falls inside the typical band."""
    labels = _labels_for(config, modality, family, feature)
    label = _classify_single(config, modality, family, feature, low_edge)
    assert label.status is OutcomeStatus.OK
    assert label.value == labels[1]


@pytest.mark.parametrize(
    "modality,family,feature,low_edge,high_edge", _FIXED_BAND_FEATURES
)
def test_fixed_bands_upper_boundary_is_typical(
    config, modality, family, feature, low_edge, high_edge
):
    """The upper band edge itself falls inside the typical band."""
    labels = _labels_for(config, modality, family, feature)
    label = _classify_single(config, modality, family, feature, high_edge)
    assert label.status is OutcomeStatus.OK
    assert label.value == labels[1]


@pytest.mark.parametrize(
    "modality,family,feature,low_edge,high_edge", _FIXED_BAND_FEATURES
)
def test_fixed_bands_just_below_low_edge_is_low(
    config, modality, family, feature, low_edge, high_edge
):
    """A value strictly below the low edge is classified as the low band."""
    labels = _labels_for(config, modality, family, feature)
    # Use a small negative offset scaled to the edge so it works for both
    # integer edges (e.g. 110) and fractional edges (e.g. 0.15, 0.30).
    below = low_edge - max(abs(low_edge), 1) * 1e-6
    label = _classify_single(config, modality, family, feature, below)
    assert label.status is OutcomeStatus.OK
    assert label.value == labels[0]


@pytest.mark.parametrize(
    "modality,family,feature,low_edge,high_edge", _FIXED_BAND_FEATURES
)
def test_fixed_bands_just_above_high_edge_is_high(
    config, modality, family, feature, low_edge, high_edge
):
    """A value strictly above the high edge is classified as the high band."""
    labels = _labels_for(config, modality, family, feature)
    above = high_edge + max(abs(high_edge), 1) * 1e-6
    label = _classify_single(config, modality, family, feature, above)
    assert label.status is OutcomeStatus.OK
    assert label.value == labels[2]


# ---------------------------------------------------------------------------
# baseline_delta: relative_pitch_shift_st, symmetric edges -3 / +3, and the
# missing-baseline path -> unavailable(MISSING_CALIBRATION).
# ---------------------------------------------------------------------------


def test_baseline_delta_lower_boundary_is_typical(config):
    """-3 st is inside the typical band (boundary inclusive to typical)."""
    labels = _labels_for(config, "paraverbal", "prosodic_level", "relative_pitch_shift_st")
    result = compute_paraverbal_base_labels(
        _para(relative_pitch_shift_st=-3),
        config,
        baseline_available=True,
        session_refs=None,
    )
    label = result.prosodic_level["relative_pitch_shift_st"]
    assert label.status is OutcomeStatus.OK
    assert label.value == labels[1]


def test_baseline_delta_upper_boundary_is_typical(config):
    """+3 st is inside the typical band (boundary inclusive to typical)."""
    labels = _labels_for(config, "paraverbal", "prosodic_level", "relative_pitch_shift_st")
    result = compute_paraverbal_base_labels(
        _para(relative_pitch_shift_st=3),
        config,
        baseline_available=True,
        session_refs=None,
    )
    label = result.prosodic_level["relative_pitch_shift_st"]
    assert label.status is OutcomeStatus.OK
    assert label.value == labels[1]


def test_baseline_delta_below_low_edge_is_low(config):
    """A relative shift below -3 st is classified as the low band."""
    labels = _labels_for(config, "paraverbal", "prosodic_level", "relative_pitch_shift_st")
    result = compute_paraverbal_base_labels(
        _para(relative_pitch_shift_st=-3.5),
        config,
        baseline_available=True,
        session_refs=None,
    )
    label = result.prosodic_level["relative_pitch_shift_st"]
    assert label.status is OutcomeStatus.OK
    assert label.value == labels[0]


def test_baseline_delta_above_high_edge_is_high(config):
    """A relative shift above +3 st is classified as the high band."""
    labels = _labels_for(config, "paraverbal", "prosodic_level", "relative_pitch_shift_st")
    result = compute_paraverbal_base_labels(
        _para(relative_pitch_shift_st=3.5),
        config,
        baseline_available=True,
        session_refs=None,
    )
    label = result.prosodic_level["relative_pitch_shift_st"]
    assert label.status is OutcomeStatus.OK
    assert label.value == labels[2]


def test_baseline_delta_without_baseline_is_missing_calibration(config):
    """No personal baseline -> unavailable with reason MISSING_CALIBRATION."""
    result = compute_paraverbal_base_labels(
        _para(relative_pitch_shift_st=0.0),
        config,
        baseline_available=False,
        session_refs=None,
    )
    label = result.prosodic_level["relative_pitch_shift_st"]
    assert label.status is OutcomeStatus.UNAVAILABLE
    assert label.reason is UnavailableReason.MISSING_CALIBRATION
    assert label.value is None


# ---------------------------------------------------------------------------
# session_percentiles: median_loudness (paraverbal), nod_rate_min and
# mean_smile_activation (nonverbal). Boundaries inclusive to typical against the
# supplied P25/P75; missing references -> INSUFFICIENT_REFERENCE_DATA.
# ---------------------------------------------------------------------------


def test_session_percentiles_below_p25_is_low(config):
    """A loudness below P25 is classified as the low band."""
    labels = _labels_for(config, "paraverbal", "prosodic_level", "median_loudness")
    refs = {"median_loudness": {"p25": 0.40, "p75": 0.80}}
    result = compute_paraverbal_base_labels(
        _para(median_loudness=0.30),
        config,
        baseline_available=True,
        session_refs=refs,
    )
    label = result.prosodic_level["median_loudness"]
    assert label.status is OutcomeStatus.OK
    assert label.value == labels[0]


def test_session_percentiles_equal_p25_is_typical(config):
    """A loudness equal to P25 is inside the typical band (inclusive)."""
    labels = _labels_for(config, "paraverbal", "prosodic_level", "median_loudness")
    refs = {"median_loudness": {"p25": 0.40, "p75": 0.80}}
    result = compute_paraverbal_base_labels(
        _para(median_loudness=0.40),
        config,
        baseline_available=True,
        session_refs=refs,
    )
    label = result.prosodic_level["median_loudness"]
    assert label.status is OutcomeStatus.OK
    assert label.value == labels[1]


def test_session_percentiles_equal_p75_is_typical(config):
    """A loudness equal to P75 is inside the typical band (inclusive)."""
    labels = _labels_for(config, "paraverbal", "prosodic_level", "median_loudness")
    refs = {"median_loudness": {"p25": 0.40, "p75": 0.80}}
    result = compute_paraverbal_base_labels(
        _para(median_loudness=0.80),
        config,
        baseline_available=True,
        session_refs=refs,
    )
    label = result.prosodic_level["median_loudness"]
    assert label.status is OutcomeStatus.OK
    assert label.value == labels[1]


def test_session_percentiles_above_p75_is_high(config):
    """A loudness above P75 is classified as the high band."""
    labels = _labels_for(config, "paraverbal", "prosodic_level", "median_loudness")
    refs = {"median_loudness": {"p25": 0.40, "p75": 0.80}}
    result = compute_paraverbal_base_labels(
        _para(median_loudness=0.90),
        config,
        baseline_available=True,
        session_refs=refs,
    )
    label = result.prosodic_level["median_loudness"]
    assert label.status is OutcomeStatus.OK
    assert label.value == labels[2]


def test_session_percentiles_nonverbal_nod_rate_bands(config):
    """nod_rate_min bands low/typical/high against supplied session references."""
    labels = _labels_for(config, "nonverbal", "head_gestural_feedback", "nod_rate_min")
    refs = {"nod_rate_min": {"p25": 5.0, "p75": 15.0}}

    low = compute_nonverbal_base_labels(
        _nonverbal(nod_rate_min=2.0), config, baseline_available=True, session_refs=refs
    ).head_gestural_feedback["nod_rate_min"]
    typical = compute_nonverbal_base_labels(
        _nonverbal(nod_rate_min=5.0), config, baseline_available=True, session_refs=refs
    ).head_gestural_feedback["nod_rate_min"]
    high = compute_nonverbal_base_labels(
        _nonverbal(nod_rate_min=20.0), config, baseline_available=True, session_refs=refs
    ).head_gestural_feedback["nod_rate_min"]

    assert low.value == labels[0]
    assert typical.value == labels[1]
    assert high.value == labels[2]


def test_session_percentiles_nonverbal_smile_activation_bands(config):
    """mean_smile_activation bands low/typical/high against session references."""
    labels = _labels_for(config, "nonverbal", "facial_expressivity", "mean_smile_activation")
    refs = {"mean_smile_activation": {"p25": 0.20, "p75": 0.60}}

    low = compute_nonverbal_base_labels(
        _nonverbal(mean_smile_activation=0.10),
        config,
        baseline_available=True,
        session_refs=refs,
    ).facial_expressivity["mean_smile_activation"]
    typical = compute_nonverbal_base_labels(
        _nonverbal(mean_smile_activation=0.60),
        config,
        baseline_available=True,
        session_refs=refs,
    ).facial_expressivity["mean_smile_activation"]
    high = compute_nonverbal_base_labels(
        _nonverbal(mean_smile_activation=0.90),
        config,
        baseline_available=True,
        session_refs=refs,
    ).facial_expressivity["mean_smile_activation"]

    assert low.value == labels[0]
    assert typical.value == labels[1]
    assert high.value == labels[2]


def test_session_percentiles_without_refs_is_insufficient_reference_data(config):
    """No session references -> INSUFFICIENT_REFERENCE_DATA for the feature."""
    result = compute_paraverbal_base_labels(
        _para(median_loudness=0.50),
        config,
        baseline_available=True,
        session_refs=None,
    )
    label = result.prosodic_level["median_loudness"]
    assert label.status is OutcomeStatus.INSUFFICIENT_REFERENCE_DATA
    assert label.reason is UnavailableReason.INSUFFICIENT_REFERENCE_DATA
    assert label.value is None


# ---------------------------------------------------------------------------
# binary: nod presence read from nod_count (nod_present slot). 0 -> absent,
# > 0 -> observed (boundary greater_than).
# ---------------------------------------------------------------------------


def test_binary_nod_absent_when_count_zero(config):
    """nod_count == 0 selects the 'absent' label (not greater than threshold)."""
    labels = _labels_for(config, "nonverbal", "head_gestural_feedback", "nod_present")
    result = compute_nonverbal_base_labels(
        _nonverbal(nod_count=0),
        config,
        baseline_available=True,
        session_refs=None,
    )
    label = result.head_gestural_feedback["nod_present"]
    assert label.status is OutcomeStatus.OK
    assert label.value == labels[0]
    assert labels[0] == "nod_absent"


def test_binary_nod_observed_when_count_positive(config):
    """nod_count == 1 selects the 'observed' label (greater than threshold 0)."""
    labels = _labels_for(config, "nonverbal", "head_gestural_feedback", "nod_present")
    result = compute_nonverbal_base_labels(
        _nonverbal(nod_count=1),
        config,
        baseline_available=True,
        session_refs=None,
    )
    label = result.head_gestural_feedback["nod_present"]
    assert label.status is OutcomeStatus.OK
    assert label.value == labels[1]
    assert labels[1] == "nod_observed"


# ---------------------------------------------------------------------------
# four_band: smile_activity_ratio with breaks [0.0, 0.10, 0.35] and
# inclusive_middle boundaries. 0.0 -> absent, 0.05 -> sparse,
# 0.10 and 0.35 -> moderate, 0.36 -> frequent.
# ---------------------------------------------------------------------------


def _smile_ratio_label(config, value):
    result = compute_nonverbal_base_labels(
        _nonverbal(smile_activity_ratio=value),
        config,
        baseline_available=True,
        session_refs=None,
    )
    return result.facial_expressivity["smile_activity_ratio"]


def test_four_band_smile_absent_at_zero(config):
    """A ratio of exactly 0.0 is the 'absent' band (band[0])."""
    labels = _labels_for(config, "nonverbal", "facial_expressivity", "smile_activity_ratio")
    label = _smile_ratio_label(config, 0.0)
    assert label.status is OutcomeStatus.OK
    assert label.value == labels[0]


def test_four_band_smile_sparse_between_zero_and_first_break(config):
    """0 < ratio < 0.10 is the 'sparse' band (band[1])."""
    labels = _labels_for(config, "nonverbal", "facial_expressivity", "smile_activity_ratio")
    label = _smile_ratio_label(config, 0.05)
    assert label.value == labels[1]


def test_four_band_smile_moderate_at_lower_middle_break(config):
    """A ratio of exactly 0.10 is inside the 'moderate' band (inclusive middle)."""
    labels = _labels_for(config, "nonverbal", "facial_expressivity", "smile_activity_ratio")
    label = _smile_ratio_label(config, 0.10)
    assert label.value == labels[2]


def test_four_band_smile_moderate_at_upper_middle_break(config):
    """A ratio of exactly 0.35 is inside the 'moderate' band (inclusive middle)."""
    labels = _labels_for(config, "nonverbal", "facial_expressivity", "smile_activity_ratio")
    label = _smile_ratio_label(config, 0.35)
    assert label.value == labels[2]


def test_four_band_smile_frequent_above_upper_break(config):
    """A ratio above 0.35 is the 'frequent' band (band[3])."""
    labels = _labels_for(config, "nonverbal", "facial_expressivity", "smile_activity_ratio")
    label = _smile_ratio_label(config, 0.36)
    assert label.value == labels[3]


# ---------------------------------------------------------------------------
# Missing feature (None) -> unavailable FamilyLabel with FEATURE_UNAVAILABLE.
# ---------------------------------------------------------------------------


def test_missing_paraverbal_feature_is_feature_unavailable(config):
    """A None processed value yields feature_unavailable, not a fabricated band."""
    result = compute_paraverbal_base_labels(
        _para(speech_rate_wpm=None),
        config,
        baseline_available=True,
        session_refs=None,
    )
    label = result.temporal["speech_rate_wpm"]
    assert label.status is OutcomeStatus.UNAVAILABLE
    assert label.reason is UnavailableReason.FEATURE_UNAVAILABLE
    assert label.value is None


def test_missing_nonverbal_feature_is_feature_unavailable(config):
    """A None nonverbal value yields feature_unavailable for that feature."""
    result = compute_nonverbal_base_labels(
        _nonverbal(visual_alignment_ratio=None),
        config,
        baseline_available=True,
        session_refs=None,
    )
    label = result.visual_orientation["visual_alignment_ratio"]
    assert label.status is OutcomeStatus.UNAVAILABLE
    assert label.reason is UnavailableReason.FEATURE_UNAVAILABLE
    assert label.value is None


# ---------------------------------------------------------------------------
# passthrough: interaction_context carried through unchanged.
# ---------------------------------------------------------------------------


def test_passthrough_context_speaking(config):
    """The 'speaking' interaction context is carried through as the base label."""
    result = compute_nonverbal_base_labels(
        _nonverbal(context="speaking"),
        config,
        baseline_available=True,
        session_refs=None,
    )
    label = result.head_gestural_feedback["interaction_context"]
    assert label.status is OutcomeStatus.OK
    assert label.value == "speaking"


def test_passthrough_context_listening(config):
    """The 'listening' interaction context is carried through as the base label."""
    result = compute_nonverbal_base_labels(
        _nonverbal(context="listening"),
        config,
        baseline_available=True,
        session_refs=None,
    )
    label = result.head_gestural_feedback["interaction_context"]
    assert label.status is OutcomeStatus.OK
    assert label.value == "listening"
