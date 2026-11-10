"""Five-point MediaPipe ocular calibration."""
from collections import Counter
from dataclasses import replace

import numpy as np

from app.models.calibration import MEDIAPIPE_GAZE_SOURCE as SOURCE
from app.nonverbal.gaze import GazeObservation
from app.nonverbal.gaze_calibration import (
    apply_affine, MIN_FACE_VALID_RATIO, MIN_TARGET_VALID_RATIO, MIN_TARGET_VALID_MS,
    MIN_CAMERA_VALID_MS, _valid_duration,
)
from app.nonverbal.guided_eye_geometry import mediapipe_eye_observation, build_eye_geometry_reference

CAMERA_RAW_RADIUS_LIMIT = .04
CAMERA_RAW_RADIUS_MIN = .01
MAX_MEDIAN_ERROR = .25
MAX_P90_ERROR = .35


def image_usable(shared):
    mean, std = shared.frame_brightness_mean, shared.frame_brightness_std
    return bool(mean is not None and std is not None and np.isfinite([mean,std]).all()
        and mean >= 15 and not (mean > 245 and std < 5))


def build_profile(observations, metadata):
    selected = [item for item in observations if any(t.observation_window_start_ms <= item.shared.timestamp_ms
        < t.observation_window_end_ms for t in metadata.targets)]
    faces = sum(item.shared.face_valid for item in selected)/len(selected) if selected else 0.
    usable = sum(image_usable(item.shared) for item in selected)/len(selected) if selected else 0.
    targets = {}
    for target in metadata.targets:
        items = [item for item in selected if target.observation_window_start_ms <= item.shared.timestamp_ms < target.observation_window_end_ms]
        eyes = [mediapipe_eye_observation(item.shared) for item in items]
        valid = [eye for eye,item in zip(eyes,items) if eye.valid and image_usable(item.shared)]
        duration = _valid_duration(valid,target.observation_window_start_ms,target.observation_window_end_ms)
        ratio = len(valid)/len(items) if items else 0.
        targets[target.target_id] = {"valid_ratio":ratio,"valid_duration_ms":duration,"valid_samples":len(valid),
            "eligible":ratio>=MIN_TARGET_VALID_RATIO and duration>=MIN_TARGET_VALID_MS,
            "invalid_reasons":dict(Counter(eye.state for eye in eyes if not eye.valid))}
    quality = {"version":"mediapipe_five_point_quality_v2","face_valid_ratio":faces,"image_usable_ratio":usable,
        "targets":targets,"covered_targets":sum(t["eligible"] for t in targets.values()),"geometry_stable":metadata.geometry_stable}
    reason = ("geometry" if not metadata.geometry_stable else "face" if faces<MIN_FACE_VALID_RATIO
        else "capture_quality" if usable<MIN_FACE_VALID_RATIO else "targets" if quality["covered_targets"]!=5 else None)
    clean = [item for item in selected if image_usable(item.shared)]
    allow_experimental = metadata.experimental_quality_bypass
    reference = build_eye_geometry_reference(clean,metadata,expected_target_count=5,allow_quality_failure=allow_experimental,
        max_median_error=MAX_MEDIAN_ERROR,max_p90_error=MAX_P90_ERROR)
    metrics = reference.get("quality") or {}
    quality["leave_one_target_out"] = metrics
    quality["quality_limits"] = reference.get("quality_limits") or {"median_normalized_error":MAX_MEDIAN_ERROR,"p90_normalized_error":MAX_P90_ERROR}
    if reason is None and reference.get("quality_passed") is not True:
        reason = "median_error" if metrics.get("median_normalized_error",0)>MAX_MEDIAN_ERROR else "p90_error" if metrics.get("p90_normalized_error",0)>MAX_P90_ERROR else "insufficient_gaze_samples"
    experimental = bool(reason and allow_experimental and reason != "geometry" and reference.get("affine_matrix") is not None)
    profile = {} if reason and not experimental else {"algorithm":"mediapipe_five_point_affine_v1","gaze_source":SOURCE,
        "supported_setup":"laptop_top_center_camera_v1","capture_geometry":metadata.geometry.model_dump(),
        "affine_matrix":reference["affine_matrix"],"ocular_reference":reference,"calibration_target_count":5}
    if profile and allow_experimental: profile["experimental_only"] = True
    return {"profile":profile,"quality":quality,"passed":reason is None,"failure_reason":reason,
        "experimental_quality_bypass":experimental}


def build_camera_reference(observations, metadata):
    from app.nonverbal.ccdbhg import head_pose_features
    valid = [(item,mediapipe_eye_observation(item.shared)) for item in observations if image_usable(item.shared)]
    valid = [(item,eye) for item,eye in valid if eye.valid]
    face_ratio = sum(item.shared.face_valid for item in observations)/len(observations) if observations else 0.
    usable = sum(image_usable(item.shared) for item in observations)/len(observations) if observations else 0.
    quality = {"camera_quality_version":"mediapipe_raw_lens_v1","camera_reference_units":"eye_widths",
        "camera_face_valid_ratio":face_ratio,"image_usable_ratio":usable,"geometry_stable":metadata.geometry_stable,
        "camera_radius_limit":CAMERA_RAW_RADIUS_LIMIT}
    base_reason = "geometry" if not metadata.geometry_stable else "face" if face_ratio<.8 else "capture_quality" if usable<.8 else None
    if base_reason == "geometry" or len(valid)<2:
        return {"passed":False,"failure_reason":base_reason or "camera","quality":quality}
    allow_experimental = metadata.experimental_quality_bypass
    points = np.asarray([[eye.unclipped_x,eye.unclipped_y] for _,eye in valid])
    fresh = observations[-1].shared.timestamp_ms-valid[-1][1].timestamp_ms<=150
    fallback = None
    last_reason = base_reason or "camera"
    for index,(item,eye) in enumerate(valid[:-1]):
        duration = _valid_duration([e for _,e in valid[index:]],eye.timestamp_ms,valid[-1][1].timestamp_ms+1)
        if duration<MIN_CAMERA_VALID_MS and not allow_experimental: break
        window = [o for o in observations if o.shared.timestamp_ms>=eye.timestamp_ms]
        center = np.median(points[index:],axis=0)
        p90 = float(np.percentile(np.linalg.norm(points[index:]-center,axis=1),90))
        heads=[]
        for o,_ in valid[index:]:
            try:
                matrix=np.asarray(o.shared.facial_transformation_matrix,dtype=float)
                if matrix.shape!=(4,4) or not np.isfinite(matrix).all(): continue
                pose=head_pose_features(matrix)
                if np.isfinite(pose).all(): heads.append(pose)
            except ValueError:
                continue
        if not heads: continue
        reason = (base_reason or ("camera" if duration<MIN_CAMERA_VALID_MS or len(valid[index:])/len(window)<MIN_FACE_VALID_RATIO
            else "camera_unstable" if p90>CAMERA_RAW_RADIUS_LIMIT or not fresh
            else "face" if len(heads)/len(window)<MIN_FACE_VALID_RATIO else None))
        last_reason=reason or last_reason
        head=np.median(heads,axis=0)
        radius=float(max(1.5*p90,CAMERA_RAW_RADIUS_MIN) if reason else np.clip(1.5*p90,CAMERA_RAW_RADIUS_MIN,CAMERA_RAW_RADIUS_LIMIT))
        mapped=apply_affine(center.reshape(1,2),np.asarray(metadata.affine_matrix))[0]
        candidate={"passed":reason is None,"failure_reason":reason,"experimental_quality_bypass":bool(reason and allow_experimental),
            "quality":{**quality,"camera_valid_duration_ms":duration,"camera_reference_start_ms":eye.timestamp_ms,"camera_radius_p90":p90},
            "camera_reference_center":mapped.tolist(),
            "camera_eye_reference":{"center":center.tolist(),"radius":radius,"radius_p90":p90,"units":"eye_widths"},
            "experimental_mediapipe_camera_eye_center":center.tolist(),
            "neutral_head":{"neutral_head_yaw":float(head[0]),"neutral_head_roll":float(head[1]),"neutral_head_pitch":float(head[2])}}
        if reason is None: return candidate
        if fallback is None: fallback=candidate
    if allow_experimental and fallback is not None: return fallback
    return {"passed":False,"failure_reason":last_reason,"quality":quality}

def gaze_observation(shared, profile):
    eye=mediapipe_eye_observation(shared)
    if not eye.valid: return eye
    if not image_usable(shared): return GazeObservation(shared.timestamp_ms,False,"capture_quality")
    raw=np.asarray([eye.unclipped_x,eye.unclipped_y])
    try:
        mapped=apply_affine(raw.reshape(1,2),np.asarray(profile["affine_matrix"]))[0]
        camera=profile.get("camera_eye_reference")
        lens=bool(camera and np.linalg.norm(raw-np.asarray(camera["center"]))<=camera["radius"])
        return replace(eye,state="mediapipe_camera" if lens else SOURCE,unclipped_x=float(mapped[0]),unclipped_y=float(mapped[1]))
    except (KeyError,TypeError,ValueError):
        return GazeObservation(shared.timestamp_ms,False,"invalid_calibration")


def gaze_screen_state(gaze):
    if (not gaze.valid or gaze.unclipped_x is None or gaze.unclipped_y is None
            or not np.isfinite([gaze.unclipped_x, gaze.unclipped_y]).all()):
        return "indeterminate"
    return "inside" if 0 <= gaze.unclipped_x <= 1 and 0 <= gaze.unclipped_y <= 1 else "outside"
