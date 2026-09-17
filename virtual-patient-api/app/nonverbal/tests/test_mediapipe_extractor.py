from types import SimpleNamespace

from app.nonverbal.mediapipe_extractor import observation_from_result


def test_missing_face_is_unavailable_and_preserves_timestamp():
    result = SimpleNamespace(
        face_landmarks=[], face_blendshapes=[], facial_transformation_matrixes=[]
    )
    observation = observation_from_result(123.5, None, result)
    assert observation.timestamp_ms == 123.5
    assert observation.face_valid is False
    assert observation.reason == "face_not_detected"


def test_valid_result_exposes_shared_outputs():
    category = SimpleNamespace(category_name="mouthSmileLeft", score=0.4)
    matrix = object()
    landmarks = [object()]
    result = SimpleNamespace(
        face_landmarks=[landmarks],
        face_blendshapes=[[category]],
        facial_transformation_matrixes=[matrix],
    )
    observation = observation_from_result(50.0, None, result)
    assert observation.face_valid is True
    assert observation.landmarks is landmarks
    assert observation.blendshapes == {"mouthSmileLeft": 0.4}
    assert observation.facial_transformation_matrix is matrix
