import pytest

from app.nonverbal.shared_observations import SharedFrameObservation
from app.nonverbal.smile import SMILE_THRESHOLD, aggregate_smile, extract_smile


def _frame(left=None, right=None, *, valid=True, timestamp=10.0):
    blendshapes = None if left is None else {"mouthSmileLeft": left, "mouthSmileRight": right}
    return SharedFrameObservation(timestamp, None, valid, blendshapes=blendshapes)


@pytest.mark.parametrize(("left", "right", "detected"), [
    (0.5, 0.2, False),
    (SMILE_THRESHOLD, SMILE_THRESHOLD, False),
    (0.6, 0.2, True),
])
def test_smile_requires_mean_strictly_above_threshold(left, right, detected):
    value = extract_smile(_frame(left, right))
    assert value is not None
    assert value.smile_detected is detected
    assert value.smile_activation == (left + right) / 2


def test_invalid_frames_are_excluded_from_aggregation():
    values = [extract_smile(_frame(0.5, 0.1)), extract_smile(_frame(valid=False))]
    ratio, mean = aggregate_smile([value for value in values if value is not None])
    assert ratio == 0.0
    assert mean == 0.3


def test_no_valid_blendshapes_is_unavailable():
    assert aggregate_smile([]) == (None, None)
