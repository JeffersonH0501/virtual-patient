import numpy as np

from app.nonverbal.gaze_calibration import apply_affine, fit_affine


def test_affine_fit_recovers_known_mapping():
    source = np.asarray([[0, 0], [1, 0], [0, 1], [1, 1], [.5, .5]], dtype=float)
    expected = np.asarray([[.8, .1, .05], [-.05, .9, .1]])
    target = apply_affine(source, expected)
    assert np.allclose(fit_affine(source, target), expected)


def test_interaction_gaze_includes_calibrated_camera_and_real_region():
    from app.nonverbal.gaze_calibration import classify_interaction_gaze
    area = {'x_normalized': .2, 'y_normalized': .1, 'width_normalized': .6, 'height_normalized': .8}
    assert classify_interaction_gaze((.5, .5), {}, area) == 'INSIDE'
    assert classify_interaction_gaze((.1, .5), {}, area) == 'OUTSIDE'
    assert classify_interaction_gaze((.1, .5), {}, area, camera_match=True) == 'INSIDE'
    assert classify_interaction_gaze((.1, .5), {}, None, camera_match=True) == 'INSIDE'
    assert classify_interaction_gaze(None, {}, area, camera_match=True) == 'UNAVAILABLE'
    assert classify_interaction_gaze((.5, .5), {}, None) == 'UNAVAILABLE'
    assert classify_interaction_gaze((float('nan'), .5), {}, area) == 'UNAVAILABLE'


def test_affine_fit_rejects_collinear_or_nonfinite_samples():
    import pytest
    for source in (np.asarray([[0, 0], [1, 1], [2, 2], [3, 3]]), np.full((4, 2), np.nan)):
        with pytest.raises(ValueError):
            fit_affine(source, np.zeros((4, 2)))
