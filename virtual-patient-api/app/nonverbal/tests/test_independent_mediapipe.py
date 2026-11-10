"""The five-point MediaPipe source must work with no BlazeGaze tracker/output."""
from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
from pydantic import ValidationError

from app.models.calibration import GazeCalibrationMetadata, CameraCalibrationMetadata, GAZE_TARGETS
from app.nonverbal.tests.test_guided_mediapipe_only import frame
from app.nonverbal import calibration_worker, video_observations
from app.nonverbal.mediapipe_calibration import SOURCE, build_profile, build_camera_reference, gaze_observation


def test_live_gaze_state_keeps_invalid_observations_indeterminate():
    from types import SimpleNamespace
    from app.nonverbal.mediapipe_calibration import gaze_screen_state
    assert gaze_screen_state(SimpleNamespace(valid=True, unclipped_x=.5, unclipped_y=.5)) == 'inside'
    assert gaze_screen_state(SimpleNamespace(valid=True, unclipped_x=1.1, unclipped_y=.5)) == 'outside'
    assert gaze_screen_state(SimpleNamespace(valid=False, unclipped_x=.5, unclipped_y=.5)) == 'indeterminate'
    assert gaze_screen_state(SimpleNamespace(valid=True, unclipped_x=float('nan'), unclipped_y=.5)) == 'indeterminate'


def calibration():
    targets, observations = [], []
    for i, (name, x, y) in enumerate(GAZE_TARGETS[:5]):
        start = i*3000
        targets.append(dict(target_id=name,target_order=i+1,target_normalized_x=x,target_normalized_y=y,
            target_pixel_x=x*1000,target_pixel_y=y*1000,presentation_start_ms=start,presentation_end_ms=start+3000,
            observation_window_start_ms=start+250,observation_window_end_ms=start+3000))
        observations.extend(frame(t,(x-.5)*.2,(y-.5)*.1) for t in range(start,start+3000,100))
    metadata = GazeCalibrationMetadata(gaze_source=SOURCE,targets=targets,geometry_stable=True,
        geometry=dict(viewport_width=1000,viewport_height=1000,device_pixel_ratio=1,
            orientation="landscape",video_width=1000,video_height=1000))
    return observations, metadata


def poor_calibration():
    observations,metadata=calibration()
    window=next(t for t in metadata.targets if t.target_id=="TOP_RIGHT")
    observations=[frame(item.shared.timestamp_ms,-.04,-.04) if window.observation_window_start_ms <= item.shared.timestamp_ms < window.observation_window_end_ms else item for item in observations]
    return observations,metadata


def test_quality_override_keeps_failed_metrics_and_requires_experimental_verification():
    from app.multimodal.calibration_attestation import sign_checkpoint,verify_calibration_checkpoints
    from fastapi import HTTPException
    observations,metadata=poor_calibration()
    strict=build_profile(observations,metadata)
    assert not strict["passed"] and strict["failure_reason"] in {"median_error","p90_error"}
    metadata.experimental_quality_bypass=True
    result=build_profile(observations,metadata)
    assert not result["passed"] and result["experimental_quality_bypass"] and result["profile"]
    assert result["quality"]["leave_one_target_out"]==strict["quality"]["leave_one_target_out"]
    camera_metadata=CameraCalibrationMetadata(gaze_source=SOURCE,geometry=metadata.geometry,geometry_stable=True,
        affine_matrix=result["profile"]["affine_matrix"],experimental_quality_bypass=True)
    camera=build_camera_reference([frame(t,y=-.06) for t in range(0,3000,100)],camera_metadata)
    tokens={"gaze":sign_checkpoint(42,42,"gaze",result,metadata.model_dump(mode="json")),
        "camera":sign_checkpoint(42,42,"camera",camera,camera_metadata.model_dump(mode="json"))}
    with pytest.raises(HTTPException): verify_calibration_checkpoints(42,42,tokens)
    verified=verify_calibration_checkpoints(42,42,tokens,allow_experimental=True)
    assert verified["profile"]["experimental_only"]
    missing=build_profile(observations[30:],metadata)
    assert not missing["passed"] and not missing["experimental_quality_bypass"] and not missing["profile"]


def test_camera_override_records_actual_failed_dispersion_without_clamping_it_to_the_limit():
    observations,metadata=calibration(); profile=build_profile(observations,metadata)["profile"]
    camera_metadata=CameraCalibrationMetadata(gaze_source=SOURCE,geometry=metadata.geometry,geometry_stable=True,
        affine_matrix=profile["affine_matrix"])
    moving=[frame(t,x=.2 if t%200 else -.2) for t in range(0,3000,100)]
    assert not build_camera_reference(moving,camera_metadata)["passed"]
    camera_metadata.experimental_quality_bypass=True
    result=build_camera_reference(moving,camera_metadata)
    assert not result["passed"] and result["experimental_quality_bypass"]
    assert result["camera_eye_reference"]["radius_p90"]>.04
    assert result["camera_eye_reference"]["radius"]>.04


def test_experimental_sparse_fit_does_not_claim_that_coverage_passed():
    observations,metadata=calibration()
    observations=[item for item in observations if any(t.observation_window_start_ms <= item.shared.timestamp_ms < t.presentation_start_ms+600 for t in metadata.targets)]
    metadata.experimental_quality_bypass=True
    result=build_profile(observations,metadata)
    assert result["experimental_quality_bypass"] and result["failure_reason"]=="targets"
    assert result["profile"]["ocular_reference"]["quality_passed"] is False


def test_five_point_contract_is_explicit_and_nine_point_legacy_is_not_reinterpreted():
    observations, metadata = calibration()
    assert len(metadata.targets)==5 and metadata.gaze_source==SOURCE
    payload=metadata.model_dump(); payload.pop("gaze_source")
    with pytest.raises(ValidationError): GazeCalibrationMetadata.model_validate(payload)


def test_obsolete_gaze_source_is_rejected():
    _, metadata = calibration()
    payload = metadata.model_dump()
    payload["gaze_source"] = "blazegaze"
    for index, (name, x, y) in enumerate(GAZE_TARGETS[5:], 5):
        payload["targets"].append(dict(target_id=name, target_order=index + 1,
            target_normalized_x=x, target_normalized_y=y, target_pixel_x=x * 1000,
            target_pixel_y=y * 1000, presentation_start_ms=index * 3000,
            presentation_end_ms=(index + 1) * 3000,
            observation_window_start_ms=index * 3000 + 250,
            observation_window_end_ms=(index + 1) * 3000))
    with pytest.raises(ValidationError):
        GazeCalibrationMetadata.model_validate(payload)
    payload=metadata.model_dump(); payload["targets"][1]["target_id"]="MIDDLE_LEFT"
    with pytest.raises(ValidationError): GazeCalibrationMetadata.model_validate(payload)


@pytest.mark.parametrize("median,p90,passed,reason",[(.25,.35,True,None),(.25001,.35,False,"median_error"),(.25,.35001,False,"p90_error")])
def test_official_mediapipe_quality_limits_are_25_and_35_percent(monkeypatch,median,p90,passed,reason):
    from app.nonverbal import mediapipe_calibration as module
    observations,metadata=calibration()
    reference=module.build_eye_geometry_reference
    def controlled(*args,**kwargs):
        assert kwargs["max_median_error"]==.25 and kwargs["max_p90_error"]==.35
        result=reference(*args,**kwargs)
        result["quality"].update(median_normalized_error=median,p90_normalized_error=p90)
        result["quality_passed"]=median<=.25 and p90<=.35
        result["status"]="ready" if result["quality_passed"] else "unavailable"
        return result
    monkeypatch.setattr(module,"build_eye_geometry_reference",controlled)
    result=build_profile(observations,metadata)
    assert result["passed"] is passed and result["failure_reason"]==reason
    assert result["quality"]["quality_limits"]=={"median_normalized_error":.25,"p90_normalized_error":.35}


def test_profile_approval_is_independent_of_blazegaze_and_reports_each_target(monkeypatch):
    observations,metadata=calibration()
    result=calibration_worker.process_gaze(Path("unused"),metadata,observations=observations)
    assert result["passed"]
    assert result["profile"]["gaze_source"]==SOURCE
    assert result["quality"]["covered_targets"]==5
    assert len(result["quality"]["targets"])==5
    assert result["quality"]["leave_one_target_out"]["p90_normalized_error"]<1e-10


def test_technical_failure_or_missing_target_cannot_be_approved():
    observations,metadata=calibration()
    dark=[replace(item,shared=replace(item.shared,frame_brightness_mean=0.)) for item in observations]
    assert build_profile(dark,metadata)["failure_reason"]=="capture_quality"
    assert not build_profile(observations[30:],metadata)["passed"]


def test_camera_has_its_own_raw_tolerance_and_mapped_output():
    observations,metadata=calibration(); profile=build_profile(observations,metadata)["profile"]
    camera_items=[frame(t,y=-.06) for t in range(0,3000,100)]
    camera=build_camera_reference(camera_items,CameraCalibrationMetadata(gaze_source=SOURCE,
        geometry=metadata.geometry,geometry_stable=True,affine_matrix=profile["affine_matrix"]))
    assert camera["passed"]
    assert np.allclose(camera["camera_eye_reference"]["center"],[0,-.06])
    assert 0<camera["camera_eye_reference"]["radius"]<=.04
    profile.update(camera_eye_reference=camera["camera_eye_reference"],camera_reference_center=camera["camera_reference_center"])
    eye=gaze_observation(camera_items[0].shared,profile)
    assert eye.valid and eye.state=="mediapipe_camera"
    assert not build_camera_reference(camera_items[:5],CameraCalibrationMetadata(gaze_source=SOURCE,
        geometry=metadata.geometry,geometry_stable=True,affine_matrix=profile["affine_matrix"]))["passed"]


def test_extractor_and_parallel_entry_point_never_construct_blazegaze(monkeypatch):
    observations,metadata=calibration(); profile=build_profile(observations,metadata)["profile"]
    monkeypatch.setattr(video_observations,"extract_video",lambda *args,**kwargs: iter([frame(0).shared]))
    costs={}
    result=video_observations.extract_nonverbal_video_observations(Path("unused"),calibration_profile=profile,stage_durations=costs)
    assert result[0].gaze.valid and costs["mode"]=="mediapipe_only"
    assert video_observations.extract_nonverbal_video_observations_parallel(Path("unused"),calibration_profile=profile)[0].gaze.valid


def test_turn_contract_includes_mediapipe_camera_and_interaction_area():
    observations,metadata=calibration(); profile=build_profile(observations,metadata)["profile"]
    profile["camera_eye_reference"]={"center":[0.,-.06],"radius":.01}
    items=[]
    for item in (frame(0,y=-.06),frame(100)):
        items.append(replace(item,gaze=gaze_observation(item.shared,profile)))
    raw=video_observations.build_turn_raw_features(items,video_observations.TurnWindow("turn",0,1000,"student"),
        calibration_profile=profile,interaction_area_snapshots=[{"timestampMs":0,"xNormalized":0,"yNormalized":0,
            "widthNormalized":1,"heightNormalized":1}],roi_duration_ms=1000)
    assert [item["state"] for item in raw.gaze_semantic_observations]==["INSIDE","INSIDE"]
    assert raw.extractor["gaze_source"]==SOURCE


def test_turn_coverage_uses_source_rate_when_lower_than_target():
    items = [frame(t) for t in range(0, 1000, 125)]
    items = [replace(item, shared=replace(item.shared, source_fps=8)) for item in items]
    raw = video_observations.build_turn_raw_features(
        items, video_observations.TurnWindow("turn", 0, 1000, "student"), sample_fps=15)
    assert raw.sample_fps == 8
    assert raw.video_quality["expected_frames"] == 8


def test_matching_checkpoints_bind_the_new_source_and_raw_camera_reference():
    from app.multimodal.calibration_attestation import sign_checkpoint,verify_calibration_checkpoints
    from fastapi import HTTPException
    observations,metadata=calibration()
    gaze_result=build_profile(observations,metadata)
    camera_metadata=CameraCalibrationMetadata(gaze_source=SOURCE,geometry=metadata.geometry,
        geometry_stable=True,affine_matrix=gaze_result["profile"]["affine_matrix"])
    camera=build_camera_reference([frame(t,y=-.06) for t in range(0,3000,100)],camera_metadata)
    tokens={"gaze":sign_checkpoint(42,42,"gaze",gaze_result,metadata.model_dump(mode="json")),
        "camera":sign_checkpoint(42,42,"camera",camera,camera_metadata.model_dump(mode="json"))}
    verified=verify_calibration_checkpoints(42,42,tokens)
    assert verified["profile"]["gaze_source"]==SOURCE
    assert verified["profile"]["camera_eye_reference"]==camera["camera_eye_reference"]
    wrong=camera_metadata.model_dump(mode="json"); wrong["gaze_source"]="blazegaze"
    tokens["camera"]=sign_checkpoint(42,42,"camera",camera,wrong)
    with pytest.raises(HTTPException): verify_calibration_checkpoints(42,42,tokens)


def test_unified_source_dispatch_does_not_request_a_blazegaze_tracker(monkeypatch,capsys):
    import io,json
    from unittest.mock import Mock
    from app.multimodal import isolated_worker,turn_video_queue
    observations,metadata=calibration()
    payload=metadata.model_dump(mode="json")
    payload.update(camera_reference_start_ms=15000,camera_reference_end_ms=20000)
    resources=Mock()
    resources.tracker_for.side_effect=AssertionError("BlazeGaze requested")
    monkeypatch.setattr(turn_video_queue,"PersistentTurnVideoResources",lambda: resources)
    process=Mock(return_value={"passed":True})
    monkeypatch.setattr(calibration_worker,"process_unified",process)
    monkeypatch.setattr("sys.stdin",io.StringIO(json.dumps({"command":"calibration-visual","stage":"unified",
        "request_id":"mp-only","media_path":"clip.webm","metadata":payload})+"\n"))
    isolated_worker._run_turn_video_server()
    assert process.call_args.kwargs == {}
    resources.tracker_for.assert_not_called()
    assert '"passed": true' in capsys.readouterr().out
