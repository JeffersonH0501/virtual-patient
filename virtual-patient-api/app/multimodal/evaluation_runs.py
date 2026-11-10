"""Persist reproducible evaluation snapshots without credentials or raw media."""
import hashlib
import json
from importlib.metadata import version, PackageNotFoundError
from app.models.medical_interview.interview_evaluation import InterviewEvaluationRunDB
from app.models.medical_interview import InterviewRecordingDB
from .config_loader import load_methodology_config


def _json_value(value):
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return json.loads(json.dumps(value, default=str))


def stage_evaluation_run(db, interview_id, condition, agent, inputs, payload):
    """Stage an append-only run in the caller's result transaction."""
    package_versions = {}
    for package in ("openai", "langchain-openai", "langchain-core", "pydantic"):
        try:
            package_versions[package] = version(package)
        except PackageNotFoundError:
            package_versions[package] = "unavailable"
    model = getattr(agent, "llm", None)
    model_config = {key: getattr(model, key, None) for key in (
        "model_name", "deployment_name", "temperature", "openai_api_version",
    )}
    methodology = load_methodology_config()
    documents = methodology.source_documents
    config_hashes = {name: hashlib.sha256(content).hexdigest() for name, content in documents.items()}
    recording = db.query(InterviewRecordingDB).filter(InterviewRecordingDB.medical_interview_id == interview_id).first()
    capture = recording.capture_config if recording is not None else None
    manifests = capture.get("extraction_manifests") if isinstance(capture, dict) else None
    manifests = manifests if isinstance(manifests, dict) else {}
    comparisons = {}
    for identifier, manifest in manifests.items():
        recorded_methodology = manifest.get("methodology") if isinstance(manifest, dict) else None
        recorded_hash = recorded_methodology.get("config_hash") if isinstance(recorded_methodology, dict) else None
        if isinstance(recorded_hash, str):
            comparisons[identifier] = "match" if recorded_hash == methodology.config_hash else "different"
        else:
            comparisons[identifier] = "legacy_unavailable"
    snapshot = _json_value({
        "snapshot_version": "evaluation_run_v3_functional_config",
        "inputs": {**inputs, "extraction_provenance": {
            "status": "available" if manifests else "legacy_unavailable",
            "manifests": manifests,
            "methodology_comparisons": comparisons,
        }},
        "model": model_config,
        "provider_responses": getattr(agent, "run_provenance", []),
        "package_versions": package_versions,
        "methodology_config_hashes": config_hashes,
        "methodology_config_hash": methodology.config_hash,
        "methodology_config": {name: content.decode("utf-8") for name, content in documents.items()},
        "output": payload,
    })
    run = InterviewEvaluationRunDB(
        medical_interview_id=interview_id,
        evaluation_condition=condition.value,
        snapshot=snapshot,
    )
    db.add(run)
    db.flush()
    return run.id
