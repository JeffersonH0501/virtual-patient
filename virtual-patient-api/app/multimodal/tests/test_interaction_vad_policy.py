from app.multimodal.config_loader import load_methodology_config
from app.multimodal.label_engine import integrate_nonverbal_labels, integrate_paraverbal_labels
from app.multimodal.schemas import NonverbalProcessedFeatures, ParaverbalProcessedFeatures
from app.multimodal.threshold_engine import compute_nonverbal_base_labels, compute_paraverbal_base_labels


def test_zero_nods_and_smile_do_not_require_session_references():
    config = load_methodology_config()
    values = NonverbalProcessedFeatures(nod_count=0, nod_rate_min=0, smile_activity_ratio=0, mean_smile_activation=.1)
    base = compute_nonverbal_base_labels(values, config, baseline_available=True, session_refs=None)
    result = integrate_nonverbal_labels(base, config)
    assert result.head_nods.value == 'no_nodding'
    assert result.smile_activity.value == 'absent_smile_activity'


def test_valid_f0_is_not_blocked_by_missing_loudness_reference():
    config = load_methodology_config()
    values = ParaverbalProcessedFeatures(f0_p20_p80_range_semitones=2, loudness_p20_p80_range=.1)
    base = compute_paraverbal_base_labels(values, config, baseline_available=True, session_refs=None)
    result = integrate_paraverbal_labels(base, config)
    assert result.prosodic_variability.value == 'reduced_f0_variability'


def test_zero_pause_count_has_priority_over_rate():
    config = load_methodology_config()
    values = ParaverbalProcessedFeatures(pause_count=0, pause_time_ratio=0, speech_rate_wpm=200)
    base = compute_paraverbal_base_labels(values, config, baseline_available=True, session_refs=None)
    assert integrate_paraverbal_labels(base, config).speech_timing.value == 'no_reportable_pauses'
