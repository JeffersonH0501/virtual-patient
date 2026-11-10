"""Research snapshots must identify the schema actually used for scoring."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from app.agents.schemas.evaluation import EvaluationResult
from app.multimodal import matched_control


def test_matched_control_records_the_actual_evaluation_schema(monkeypatch):
    captured = {}
    def stage(db, interview_id, condition, agent, inputs, payload):
        captured.update(inputs)
        return "synthetic-run"
    monkeypatch.setattr(matched_control, "stage_evaluation_run", stage)
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = []
    agent = SimpleNamespace(target_language="English", evaluate_multimodal=AsyncMock(return_value=[]))
    asyncio.run(matched_control.evaluate_matched_text_control(db, 7, agent,
        [{"id": 1, "role": "user", "content": "Synthetic question"}]))
    assert captured["output_schema"] == EvaluationResult.model_json_schema()
    assert "critical_turns" not in captured["output_schema"].get("properties", {})


def test_mediapipe_rejects_an_unverified_artifact_before_native_loading(tmp_path):
    import pytest
    from app.nonverbal.mediapipe_extractor import create_face_landmarker
    artifact = tmp_path / "unverified.task"
    artifact.write_bytes(b"Synthetic invalid model")
    with pytest.raises(ValueError, match="SHA-256"):
        create_face_landmarker(artifact)


def test_extraction_manifest_is_content_addressed_and_preserves_prior_versions():
    from app.multimodal.extraction_provenance import record_extraction_manifest
    recording = SimpleNamespace(capture_config={})
    original = {"manifest_version": "extraction_v1", "source_hashes": {"extractor": "old"}}
    identifier = record_extraction_manifest(recording, original)
    original["source_hashes"]["extractor"] = "mutated"
    assert recording.capture_config["extraction_manifests"][identifier]["source_hashes"]["extractor"] == "old"
    second = record_extraction_manifest(recording, original)
    assert identifier != second and len(recording.capture_config["extraction_manifests"]) == 2


def test_pipeline_layers_keep_manifest_identity_and_exact_references(monkeypatch):
    from app.multimodal import extraction_provenance
    from app.multimodal.tests.test_pipeline import (_PipelineHarness, _make_turn, _all_assets,
        _paraverbal_for, _nonverbal_for)
    captured = {}
    def build(config, *, mode, references, calibration):
        captured.update(references)
        return {"manifest_version": "extraction_v1", "references": references}
    monkeypatch.setattr(extraction_provenance, "build_extraction_manifest", build)
    turns = [_make_turn(f"t{i}", "student", i, i*4000, (i+1)*4000) for i in range(4)]
    harness = _PipelineHarness(turns=turns, assets=_all_assets(),
        paraverbal_return=_paraverbal_for([turn.id for turn in turns]), nonverbal_return=_nonverbal_for(turns))
    harness.run()
    manifests = harness.recording.capture_config["extraction_manifests"]
    assert captured["paraverbal"]["median_loudness"]["p75"] is not None
    for turn in turns:
        identifier = turn.paraverbal["raw"]["extractor"]["extraction_manifest_hash"]
        assert manifests[identifier]["references"] == captured
        assert turn.nonverbal_features["raw"]["extractor"]["labeling_manifest_hash"] == identifier


def test_evaluation_snapshot_carries_recorded_extraction_identity():
    from hashlib import sha256
    from app.multimodal.config_loader import load_methodology_config
    from app.multimodal.evaluation_runs import stage_evaluation_run
    from app.models.medical_interview.interview_evaluation import EvaluationCondition
    methodology = load_methodology_config()
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(
        capture_config={"extraction_manifests": {
            "synthetic-hash": {"manifest_version": "extraction_v1"},
            "current": {"methodology": {"config_hash": methodology.config_hash}},
            "prior": {"methodology": {"config_hash": "previous-config-hash"}},
        }})
    stage_evaluation_run(db, 7, EvaluationCondition.TEXT_ONLY, SimpleNamespace(), {}, {})
    snapshot = db.add.call_args.args[0].snapshot
    assert snapshot["inputs"]["extraction_provenance"]["manifests"]["synthetic-hash"]["manifest_version"] == "extraction_v1"
    assert snapshot["inputs"]["extraction_provenance"]["methodology_comparisons"] == {
        "synthetic-hash": "legacy_unavailable", "current": "match", "prior": "different",
    }
    assert snapshot["methodology_config_hash"] == methodology.config_hash
    for name, source in methodology.source_documents.items():
        assert snapshot["methodology_config"][name].encode("utf-8") == source
        assert snapshot["methodology_config_hashes"][name] == sha256(source).hexdigest()


def test_urlencoded_form_limits_reject_excess_fields():
    from fastapi import FastAPI, Form
    from fastapi.testclient import TestClient
    app = FastAPI()
    @app.post("/form")
    async def form(value: str = Form()):
        return {"value": value}
    with TestClient(app) as client:
        assert client.post("/form", data={"value": "synthetic"}).json() == {"value": "synthetic"}
        fields = {"value": "synthetic", **{f"field{i}": "x" for i in range(1000)}}
        response = client.post("/form", data=fields)
        assert response.status_code == 400
        assert "fields" in response.json()["detail"]
