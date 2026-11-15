"""Durable, independently regenerable feedback stored in recording metadata."""
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from app.models.medical_interview.interview_recording import InterviewRecordingDB, InterviewTurnDB
from app.models.medical_interview.interview_evaluation import InterviewEvaluationDB
from app.models.processing_job import InterviewProcessingJobDB
from app.controllers.medical_interview_controller import MedicalInterviewController
from app.agents.prompts.multimodal_evaluation import MULTIMODAL_EVALUATION_CONFIG, get_multimodal_metadata
from app.agents.prompts.learning_moments import get_learning_moment_prompts, get_strength_moment_prompts, PROMPT_VERSION
from app.agents.schemas.learning_moments import LearningMomentReferenceError, LearningMomentOutput, validate_moment
from .conversation_formatter import MultimodalConversationFormatter

logger = logging.getLogger(__name__)


def _hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, ensure_ascii=False).encode()).hexdigest()


def build_context(db, interview_id, recording):
    evaluations = db.query(InterviewEvaluationDB).filter(InterviewEvaluationDB.medical_interview_id == interview_id).all()
    conditions = {row.evaluation_condition: row for row in evaluations}
    if not {"TEXT_ONLY", "TEXT_PLUS_MULTIMODAL"}.issubset(conditions):
        raise ValueError("Both persisted evaluation conditions are required")
    source = MedicalInterviewController(db)
    data = source.get_interview_evaluation_data(interview_id)
    messages = source.format_messages_for_evaluation(data["messages"])
    turns = db.query(InterviewTurnDB).filter(InterviewTurnDB.medical_interview_id == interview_id).all()
    # One enriched transcript per category (same T# aliases, category-specific
    # evidence embedded) plus the alias->UUID map, shared by all categories
    # because aliases are assigned in deterministic conversation order.
    transcripts = {}
    evidence = {}
    alias_to_turn_id = {}
    for category in MULTIMODAL_EVALUATION_CONFIG:
        formatted = MultimodalConversationFormatter.format_messages(messages, turns, category)
        transcripts[category] = formatted.text
        evidence[category] = formatted.evidence_by_turn
        alias_to_turn_id = formatted.alias_to_turn_id
    evaluation = conditions["TEXT_PLUS_MULTIMODAL"]
    results = {item["aspect"]: item for item in evaluation.evaluation_results if item["aspect"] in evidence}
    run_id = (recording.capture_config or {}).get("evaluation_processing", {}).get("run_id")
    evidence_hash = _hash([{key: getattr(turn, key) for key in ("id", "message_id", "speaker", "paraverbal", "nonverbal_features", "timing_quality")} for turn in sorted(turns, key=lambda item: str(item.id))])
    language = data.get("interview_metadata", {}).get("patient_response_language") if isinstance(data.get("interview_metadata"), dict) else None
    interview = recording.medical_interview
    language = language or (interview.interview_metadata or {}).get("patient_response_language") or getattr(interview.user, "preferred_language", "en")
    criteria = {item["aspect"]: item["criteria"] for item in get_multimodal_metadata("es" if language == "es" else "en")}
    context = {"transcripts": transcripts, "turn_ids": sorted(alias_to_turn_id), "evidence": evidence,
               "alias_to_turn_id": alias_to_turn_id, "criteria": criteria,
               "evaluations": {aspect: {key: item[key] for key in ("score", "feedback")} for aspect, item in results.items()},
               "response_language": "Spanish" if language == "es" else "English"}
    return context, _hash({"context": context, "evidence_hash": evidence_hash, "evaluation_id": evaluation.id, "run_id": run_id, "prompt": PROMPT_VERSION}), run_id, evidence_hash


def recording_for(db, interview_id, *, lock=False):
    query = db.query(InterviewRecordingDB).filter(InterviewRecordingDB.medical_interview_id == interview_id)
    return (query.with_for_update() if lock else query).first()


def _save(recording, state):
    recording.capture_config = {**(recording.capture_config or {}), "learning_moments": state}


def build_category_message(context, category):
    """Labeled sections for one category: transcript, per-turn evidence keys,

    criteria and the prior category evaluation. The transcript already embeds the
    evidence descriptions; the explicit EVIDENCE BY TURN list enumerates the valid
    evidence keys per turn so the model cites only what exists (and for validation).
    """
    evidence = context["evidence"].get(category, {})
    evidence_lines = [f"{alias}: {', '.join(sorted(families))}" for alias, families in sorted(evidence.items())] or ["(no multimodal evidence available)"]
    evaluation = context["evaluations"].get(category, {})
    criteria = context["criteria"].get(category, [])
    return (
        f"RESPONSE LANGUAGE: {context['response_language']}\n\n"
        "=== TRANSCRIPT (START) ===\n"
        f"{context['transcripts'][category]}\n"
        "=== TRANSCRIPT (END) ===\n\n"
        "=== EVIDENCE BY TURN (valid evidence keys you may cite) ===\n"
        f"{chr(10).join(evidence_lines)}\n\n"
        "=== CRITERIA FOR THIS CATEGORY ===\n"
        f"{chr(10).join(f'- {item}' for item in criteria)}\n\n"
        "=== PRIOR EVALUATION FOR THIS CATEGORY (context only) ===\n"
        f"Score: {evaluation.get('score', 'n/a')}\n"
        f"Feedback: {evaluation.get('feedback', 'n/a')}"
    )


async def _generate_category_moment(model, prompt, category, context, provenance, interview_id):
    """Run one category prompt and return its validated moment, or None.

    One retry on reference-validation failure. A category that still fails
    validation after the retry contributes no moment (returns None) and never
    aborts the other categories: an unsupported citation means "no moment here",
    not a job failure. Only genuine technical/schema failures propagate.
    """
    from langchain_core.messages import SystemMessage, HumanMessage
    from app.agents.evaluation_provenance import EvaluationProvenanceCallback
    messages = [SystemMessage(content=prompt), HumanMessage(content=build_category_message(context, category))]
    for attempt in range(2):
        response = await model.ainvoke(messages,
            config={"callbacks": [EvaluationProvenanceCallback(provenance, f"learning_moments_{category}", prompt, messages)]})
        parsed = response.get("parsed")
        if parsed is None:
            # Validate tool arguments directly so schema errors remain diagnosable.
            calls = getattr(response.get("raw"), "tool_calls", [])
            if calls:
                parsed = LearningMomentOutput.model_validate(calls[0]["args"])
            else:
                raise ValueError("Learning moment structured output failed") from response.get("parsing_error")
        try:
            return validate_moment(LearningMomentOutput.model_validate(parsed).moment, category, context)
        except LearningMomentReferenceError as exc:
            if attempt:
                # The retry still did not ground its citation; skip this category
                # rather than failing the whole interview's feedback.
                logger.warning("Skipping learning moment interview_id=%s category=%s after retry reason=%s", interview_id, category, exc)
                return None
            logger.warning("Retrying learning moment interview_id=%s category=%s reason=%s", interview_id, category, exc)
            messages.append(HumanMessage(content=(
                f"The previous output failed validation: {exc}. Return {{\"moment\": null}} unless there is a "
                "clearly specific, severe moment grounded in paraverbal or nonverbal evidence. Cite only turn "
                "aliases present in the transcript (such as T1). evidence_used must include at least one "
                "paraverbal or nonverbal key shown for that exact turn in EVIDENCE BY TURN; never use \"text\" "
                "alone. If no such key fits the cited turn, return {{\"moment\": null}}. Use at most two turns and "
                "never mention turn identifiers or numbers in the text."
            )))


def queue_learning_moments(db, interview_id, *, force=False):
    from .processing_jobs import stage_processing_job
    recording = recording_for(db, interview_id, lock=True)
    if recording is None:
        raise ValueError("Interview recording metadata is required")
    context, source_hash, _, _ = build_context(db, interview_id, recording)
    state = (recording.capture_config or {}).get("learning_moments", {})
    active = db.query(InterviewProcessingJobDB).filter(InterviewProcessingJobDB.medical_interview_id == interview_id,
        InterviewProcessingJobDB.kind == "learning_moments", InterviewProcessingJobDB.status.in_(["queued", "processing"])).first()
    if active or (not force and state.get("status") == "completed" and state.get("source_hash") == source_hash):
        db.commit()
        return
    _save(recording, {**state, "status": "pending", "requested_source_hash": source_hash, "error_code": None})
    stage_processing_job(db, interview_id, "learning_moments", {"recording_id": recording.id, "force": force})
    db.commit()


def read_learning_moments(db, interview_id):
    recording = recording_for(db, interview_id)
    state = dict((recording.capture_config or {}).get("learning_moments", {})) if recording else {}
    stale = False
    try:
        _, current_hash, _, _ = build_context(db, interview_id, recording)
        stale = bool(state.get("source_hash") and state["source_hash"] != current_hash)
        capture = recording.capture_config or {}
        stale |= any(capture.get(key, {}).get("status") in {"queued", "processing", "stale"} for key in ("observation_processing", "evaluation_processing"))
    except (ValueError, AttributeError):
        stale = True
    return {**state, "status": state.get("status", "not_generated"), "stale": stale,
            "moments": [] if stale else state.get("moments", [])}


async def generate_learning_moments(interview_id, recording_id, force=False):
    from app.core.database import SessionLocal
    with SessionLocal() as db:
        await _run_generation(db, interview_id, recording_id, force)


async def _run_generation(db, interview_id, recording_id, force):
    from app.agents.evaluation_agent import EvaluationAgent
    if True:
        try:
            recording = recording_for(db, interview_id, lock=True)
            if recording is None or recording.id != recording_id:
                raise ValueError("Interview recording unavailable")
            context, source_hash, run_id, evidence_hash = build_context(db, interview_id, recording)
            previous = (recording.capture_config or {}).get("learning_moments", {})
            if not force and previous.get("status") == "completed" and previous.get("source_hash") == source_hash:
                return
            _save(recording, {**previous, "status": "processing", "error_code": None})
            db.commit()
            agent = EvaluationAgent(target_language=context["response_language"])
            provenance = []
            model = agent.llm.with_structured_output(LearningMomentOutput, method="function_calling", include_raw=True)
            alias_to_turn_id = context["alias_to_turn_id"]
            improvement_prompts = get_learning_moment_prompts(context["response_language"])
            strength_prompts = get_strength_moment_prompts(context["response_language"])
            # One independent call per category per type; each yields at most one moment.
            moments = []
            for category in improvement_prompts:
                # Generate improvement moment
                improvement_moment = await _generate_category_moment(
                    model, improvement_prompts[category], category, context, provenance, interview_id,
                )
                if improvement_moment is not None:
                    improvement_moment.moment_type = "improvement"
                    improvement_moment.turn_ids = [alias_to_turn_id[alias] for alias in improvement_moment.turn_ids]
                    moments.append(improvement_moment)
                
                # Generate strength moment
                strength_moment = await _generate_category_moment(
                    model, strength_prompts[category], category, context, provenance, interview_id,
                )
                if strength_moment is not None:
                    strength_moment.moment_type = "strength"
                    strength_moment.turn_ids = [alias_to_turn_id[alias] for alias in strength_moment.turn_ids]
                    moments.append(strength_moment)
            # Re-read after the network call; never publish feedback for superseded inputs.
            db.expire_all()
            recording = recording_for(db, interview_id, lock=True)
            if build_context(db, interview_id, recording)[1] != source_hash:
                raise ValueError("Learning moments source changed during generation")
            generation_id = str(uuid.uuid4())
            _save(recording, {"status": "completed", "moments": [{"id": str(uuid.uuid4()), **moment.model_dump()} for moment in moments],
                "source_hash": source_hash, "evaluation_run_id": run_id, "evidence_hash": evidence_hash,
                "prompt_version": PROMPT_VERSION, "generation_id": generation_id, "generated_at": datetime.now(timezone.utc).isoformat(),
                "model": str(getattr(agent.llm, "model_name", "configured_deployment")), "provider_provenance": provenance, "error_code": None})
            db.commit()
        except Exception as exc:
            # Log only error classes and schema locations, never model arguments,
            # transcripts or provider exception messages (which may contain data).
            import traceback
            from pydantic import ValidationError
            cause = exc.__cause__ or exc
            details = [{"field": ".".join(str(part) for part in error["loc"]), "type": error["type"]}
                       for error in cause.errors(include_input=False)] if isinstance(cause, ValidationError) else []
            frames = traceback.extract_tb(exc.__traceback__)
            logger.error("Learning moments generation failed interview_id=%s error_type=%s cause_type=%s phase=%s schema_errors=%s",
                         interview_id, type(exc).__name__, type(cause).__name__, frames[-1].name if frames else "unknown", details)
            db.rollback()
            recording = recording_for(db, interview_id, lock=True)
            if recording:
                _save(recording, {**(recording.capture_config or {}).get("learning_moments", {}), "status": "failed", "error_code": "learning_moments_generation_failed"})
                db.commit()
