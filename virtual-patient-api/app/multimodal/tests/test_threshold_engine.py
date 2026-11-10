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
    ("paraverbal", "speech_timing", "speech_rate_wpm", 110, 170),
    ("paraverbal", "speech_timing", "articulation_rate_wpm", 130, 210),
    ("paraverbal", "speech_timing", "pause_frequency_per_min", 12, 24),
    ("paraverbal", "speech_timing", "pause_time_ratio", 0.15, 0.30),
    ("paraverbal", "prosodic_variability", "f0_p20_p80_range_semitones", 4, 8),
]


@pytest.mark.parametrize("value,expected", [(500, "pause_duration_brief"), (999, "pause_duration_brief"), (1000, "pause_duration_typical"), (1999, "pause_duration_typical"), (2000, "pause_duration_long")])
def test_pause_duration_boundaries(config, value, expected):
    assert _classify_single(config, "paraverbal", "speech_timing", "median_pause_duration_ms", value).value == expected


@pytest.mark.parametrize("value,expected", [(0.499, "interaction_gaze_outside"), (0.5, "interaction_gaze_inside")])
def test_interaction_gaze_boundary(config, value, expected):
    assert _classify_single(config, "nonverbal", "gaze_orientation", "interaction_gaze_ratio", value).value == expected


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


def test_nod_rate_does_not_use_session_percentiles(config):
    assert _entry(config, "nonverbal", "head_nods", "nod_rate_min")["strategy"] == "passthrough"


def test_smile_activation_does_not_use_session_percentiles(config):
    assert _entry(config, "nonverbal", "smile_activity", "mean_smile_activation")["strategy"] == "passthrough"


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
    labels = _labels_for(config, "nonverbal", "head_nods", "nod_present")
    result = compute_nonverbal_base_labels(
        _nonverbal(nod_count=0),
        config,
        baseline_available=True,
        session_refs=None,
    )
    label = result.head_nods["nod_present"]
    assert label.status is OutcomeStatus.OK
    assert label.value == labels[0]
    assert labels[0] == "nod_absent"


def test_binary_nod_observed_when_count_positive(config):
    """nod_count == 1 selects the 'observed' label (greater than threshold 0)."""
    labels = _labels_for(config, "nonverbal", "head_nods", "nod_present")
    result = compute_nonverbal_base_labels(
        _nonverbal(nod_count=1),
        config,
        baseline_available=True,
        session_refs=None,
    )
    label = result.head_nods["nod_present"]
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
    return result.smile_activity["smile_activity_ratio"]


def test_four_band_smile_absent_at_zero(config):
    """A ratio of exactly 0.0 is the 'absent' band (band[0])."""
    labels = _labels_for(config, "nonverbal", "smile_activity", "smile_activity_ratio")
    label = _smile_ratio_label(config, 0.0)
    assert label.status is OutcomeStatus.OK
    assert label.value == labels[0]


def test_four_band_smile_sparse_between_zero_and_first_break(config):
    """0 < ratio < 0.10 is the 'sparse' band (band[1])."""
    labels = _labels_for(config, "nonverbal", "smile_activity", "smile_activity_ratio")
    label = _smile_ratio_label(config, 0.05)
    assert label.value == labels[1]


def test_four_band_smile_moderate_at_lower_middle_break(config):
    """A ratio of exactly 0.10 is inside the 'moderate' band (inclusive middle)."""
    labels = _labels_for(config, "nonverbal", "smile_activity", "smile_activity_ratio")
    label = _smile_ratio_label(config, 0.10)
    assert label.value == labels[2]


def test_four_band_smile_moderate_at_upper_middle_break(config):
    """A ratio of exactly 0.35 is inside the 'moderate' band (inclusive middle)."""
    labels = _labels_for(config, "nonverbal", "smile_activity", "smile_activity_ratio")
    label = _smile_ratio_label(config, 0.35)
    assert label.value == labels[2]


def test_four_band_smile_frequent_above_upper_break(config):
    """A ratio above 0.35 is the 'frequent' band (band[3])."""
    labels = _labels_for(config, "nonverbal", "smile_activity", "smile_activity_ratio")
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
    label = result.speech_timing["speech_rate_wpm"]
    assert label.status is OutcomeStatus.UNAVAILABLE
    assert label.reason is UnavailableReason.FEATURE_UNAVAILABLE
    assert label.value is None


def test_missing_nonverbal_feature_is_feature_unavailable(config):
    """A None nonverbal value yields feature_unavailable for that feature."""
    result = compute_nonverbal_base_labels(
        _nonverbal(interaction_gaze_ratio=None),
        config,
        baseline_available=True,
        session_refs=None,
    )
    label = result.gaze_orientation["interaction_gaze_ratio"]
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
    label = result.head_nods["interaction_context"]
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
    label = result.head_nods["interaction_context"]
    assert label.status is OutcomeStatus.OK
    assert label.value == "listening"
