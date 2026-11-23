"""Enrich the canonical messages without replacing their text or order."""

from dataclasses import dataclass, field
from sqlalchemy.orm import Session
from app.models.medical_interview.interview_recording import InterviewTurnDB
from app.agents.prompts.multimodal_evaluation import MULTIMODAL_EVALUATION_CONFIG
from .evidence_text import render_family_evidence


@dataclass(frozen=True)
class EnrichedConversation:
    text: str
    turn_ids: frozenset[str]
    has_valid_evidence: bool = False
    canonical_text: str = ""
    evidence_by_turn: dict = field(default_factory=dict)
    # Stable, human-readable turn labels (T1, T2, ...) mapped to their database UUIDs.
    # Both the evaluation and learning-moments flows cite turns by these aliases.
    alias_to_turn_id: dict = field(default_factory=dict)


# Where each speaker's window comes from: the student's speech from its onset in their own clip, and the patient's
# complete, confirmed TTS playback. Any other source (for example written delivery) has no verified window.
_VERIFIED_WINDOW_SOURCE = {"student": "turn_media", "patient": "tts_playback"}
def analysed_window_seconds(turn) -> float | None:
    """Length of the window the turn's evidence was computed over, or None when it is not verified.
    For the patient this is the confirmed playback, so waiting for the reply is never included. Provisional or
    unavailable timing, or a window that does not run forward, has no reliable duration and is omitted.
    """
    start, end = getattr(turn, "start_ms", None), getattr(turn, "end_ms", None)
    if (getattr(turn, "timing_quality", None) != "measured"
            or getattr(turn, "timing_source", None) != _VERIFIED_WINDOW_SOURCE.get(getattr(turn, "speaker", None))
            or not isinstance(start, (int, float)) or not isinstance(end, (int, float)) or end <= start):
        return None
    return (end - start) / 1000
class MultimodalConversationFormatter:
    def __init__(self, db: Session):
        self.db = db

    def load(self, interview_id: int, aspect: str, messages) -> EnrichedConversation:
        turns = self.db.query(InterviewTurnDB).filter(
            InterviewTurnDB.medical_interview_id == interview_id,
        ).all()
        return self.format_messages(messages, turns, aspect)

    @staticmethod
    def format_messages(messages, turns, aspect: str, *, include_evidence: bool = True, config_override=None, render_evidence=True) -> EnrichedConversation:
        config = config_override or MULTIMODAL_EVALUATION_CONFIG[aspect]
        turns_by_message = {turn.message_id: turn for turn in turns if turn.message_id is not None}
        blocks, canonical = [], []
        identifiers = set()
        has_valid_evidence = False
        evidence_by_turn = {}
        alias_to_turn_id = {}
        for message in messages:
            role = message.get("role", "unknown")
            content = message.get("content", "")
            doctor = role == "user" or "human" in role.lower()
            patient = role == "assistant" or "ai" in role.lower()
            speaker = "DOCTOR" if doctor else "PATIENT" if patient else role.title()
            # Match EvaluationAgent._format_conversation exactly, including multiline text.
            text = f"{speaker}: {content}"
            canonical.append(text)
            turn = turns_by_message.get(message.get("id"))
            expected = "student" if doctor else "patient" if patient else None
            if turn is None or turn.speaker != expected:
                blocks.append(text)
                continue
            identifiers.add(turn.id)
            # Assign a short, stable alias in conversation order; the UUID never
            # reaches the model, only the alias used for citation and validation.
            alias = f"T{len(alias_to_turn_id) + 1}"
            alias_to_turn_id[alias] = str(turn.id)
            modalities = []
            if turn.speaker in config["nonverbal_speakers"]:
                modalities.append((turn.nonverbal_features, config["nonverbal"]))
            if doctor:
                modalities.append((turn.paraverbal, config["paraverbal"]))
            # The duration belongs only to turns this category receives evidence for: it is the window that evidence
            # describes, so it is not given for turns whose behavior the category does not read.
            header = f"[TURN {alias} speaker={speaker}"
            duration = analysed_window_seconds(turn) if any(families for _, families in modalities) else None
            lines = [f"{header}{f' duration={duration:.1f}s' if duration is not None else ''}]", text]
            if patient and getattr(turn, "timing_quality", None) == "provisional":
                lines.append("[PLAYBACK: completion was not confirmed; do not assume the entire patient message was heard.]")
            evidence_lines = []
            valid_evidence = {}
            for payload, families in modalities:
                for family in families:
                    description = render_family_evidence(payload or {}, family) if include_evidence else None
                    has_valid_evidence |= description is not None
                    name = config["family_display_names"][family]
                    if description is not None:
                        evidence_lines.append(f"- {name}: {description}")
                        valid_evidence[family] = f"{name}: {description}"
            if valid_evidence:
                evidence_by_turn[alias] = valid_evidence
            if evidence_lines and render_evidence:
                heading = "DOCTOR SPEECH DELIVERY" if aspect == "speak_clearly" else f"DOCTOR BEHAVIOR WHILE {'SPEAKING' if doctor else 'LISTENING'}"
                lines.extend([f"{heading}:", *evidence_lines])
            blocks.append("\n".join(lines))
        return EnrichedConversation("\n\n".join(blocks), frozenset(identifiers),
                                    has_valid_evidence, "\n\n".join(canonical), evidence_by_turn, alias_to_turn_id)
