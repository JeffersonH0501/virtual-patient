import pytest
from app.media.patient_roi import slice_patient_roi_snapshots


def sample(time, x=.2):
    return dict(timestampMs=time, xNormalized=x, yNormalized=.2, widthNormalized=.2, heightNormalized=.2)


def test_clip_carries_the_last_region_forward_and_keeps_changes_inside_it():
    source = [sample(0), sample(500, .3), sample(1200, .4), sample(1800, .5)]
    result = slice_patient_roi_snapshots(source, 1000, 500)
    assert [(item['timestamp_ms'], item['x_normalized']) for item in result] == [(0, .3), (200, .4)]
    assert source[1]['timestampMs'] == 500


def test_snapshot_at_clip_start_replaces_the_previous_region():
    result = slice_patient_roi_snapshots([sample(0), sample(1000, .4)], 1000, 500)
    assert len(result) == 1 and result[0]['timestamp_ms'] == 0 and result[0]['x_normalized'] == .4


def test_future_region_is_not_backdated_and_missing_timeline_stays_empty():
    result = slice_patient_roi_snapshots([sample(1200)], 1000, 500)
    assert result[0]['timestamp_ms'] == 200
    assert slice_patient_roi_snapshots([], 1000, 500) == []


@pytest.mark.parametrize('source', [None, [None], [sample(-1)], [sample(500), sample(100)]])
def test_invalid_historical_region_is_unavailable(source):
    assert slice_patient_roi_snapshots(source, 1000, 500) is None
