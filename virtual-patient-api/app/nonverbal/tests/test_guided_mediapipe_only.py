"""MediaPipe-only classification must not consume BlazeGaze predictions."""
from dataclasses import replace
from types import SimpleNamespace

import numpy as np

from app.models.calibration import GAZE_TARGETS
from app.nonverbal.gaze import GazeObservation
from app.nonverbal.shared_observations import SharedFrameObservation
from app.nonverbal.video_observations import EnrichedFrameObservation
from app.nonverbal.guided_eye_geometry import build_eye_geometry_reference


def frame(timestamp, x=0., y=0., face=True, brightness=100.):
    landmarks = [SimpleNamespace(x=0., y=0., z=0.) for _ in range(478)]
    for left, right, lids, irises, origin in (
            (33,133,(160,158,153,144),(469,470,471,472),.3),
            (362,263,(385,387,373,380),(474,475,476,477),.6)):
        for index, px, py in ((left,origin,.4),(right,origin+.1,.4),
                (lids[0],origin+.02,.38),(lids[1],origin+.08,.38),
                (lids[2],origin+.08,.42),(lids[3],origin+.02,.42)):
            landmarks[index] = SimpleNamespace(x=px,y=py,z=0.)
        for index in irises:
            landmarks[index] = SimpleNamespace(x=origin+.05+x*.1,y=.4+y*.1,z=0.)
    shared = SharedFrameObservation(timestamp,None,face,landmarks=landmarks,
        facial_transformation_matrix=np.eye(4),frame_width=1000,frame_height=1000,
        frame_brightness_mean=brightness,frame_brightness_std=20.)
    return EnrichedFrameObservation(shared,None,GazeObservation(timestamp,False,"inference_failed"))


def test_b_calibration_and_camera_reference_work_when_blazegaze_has_no_predictions():
    observations, targets = [], []
    for i,(name,x,y) in enumerate(GAZE_TARGETS[:5]):
        start=i*2000
        targets.append(SimpleNamespace(target_id=name,observation_window_start_ms=start,
            observation_window_end_ms=start+2000,target_normalized_x=x,target_normalized_y=y))
        observations.extend(frame(t,(x-.5)*.2,(y-.5)*.1) for t in range(start,start+2000,100))
    metadata=SimpleNamespace(targets=targets,geometry=SimpleNamespace(viewport_width=1000,viewport_height=1000))
    reference=build_eye_geometry_reference(observations,metadata,expected_target_count=5)
    assert reference["status"] == "ready"
    assert reference["quality"]["p90_normalized_error"] < 1e-10


