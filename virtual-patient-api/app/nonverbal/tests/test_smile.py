from app.nonverbal.shared_observations import SharedFrameObservation
from app.nonverbal.smile import SMILE_THRESHOLD, aggregate_smile, extract_smile


def _frame(left=None, right=None, *, valid=True, timestamp=10.0):
    blendshapes = None if left is None else {"mouthSmileLeft": left, "mouthSmileRight": right}
    return SharedFrameObservation(timestamp, None, valid, blendshapes=blendshapes)


def test_smile_threshold_and_activation():
    value = extract_smile(_frame(SMILE_THRESHOLD, 0.1))
    assert value is not None
    assert value.smile_detected is True
    assert value.smile_activation == (SMILE_THRESHOLD + 0.1) / 2


def test_invalid_frames_are_excluded_from_aggregation():
    values = [extract_smile(_frame(0.5, 0.1)), extract_smile(_frame(valid=False))]
    ratio, mean = aggregate_smile([value for value in values if value is not None])
    assert ratio == 1.0
    assert mean == 0.3


def test_no_valid_blendshapes_is_unavailable():
    assert aggregate_smile([]) == (None, None)
