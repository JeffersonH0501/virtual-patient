"""Tests for the multimodal pipeline orchestration.

Covers Requirements 28.6 (pipeline tests: happy path, partial audio, partial
video, missing calibration, extraction failure, database persistence, and
version persistence) plus 24.2 (single-modality failure yields ``partial``, never
``failed``) and 6.1-6.3 (``versions`` and ``config_hash`` persisted on every
layer, deterministic and matching the loaded methodology config).

Isolation strategy
------------------
``process_multimodal_interview`` normally opens a real ``SessionLocal`` DB
session, reads media assets, and drives OpenSMILE / Py-Feat over real media.
None of that is available (or desirable) in a unit-test environment, so these
tests patch, on the ``app.multimodal.pipeline`` module:

* ``SessionLocal``  -> returns a :class:`_FakeSession` whose ``.query(Model)``
  dispatches by ORM model to the right in-memory stub list/object and whose
  ``.commit()`` calls are counted.
* ``get_media_storage`` -> returns a stub storage whose ``.resolve(key)`` yields
  a dummy path (never touched, because the extractors are also patched).
* ``analyze_student_turns`` / ``analyze_openface_student_turn_videos`` -> return
  in-memory raw features (real ``ParaverbalRawFeatures`` objects and the raw
  OpenFace 3.0 payload dict shape) so no media / OpenSMILE / OpenFace 3.0 runs.
* ``read_personal_baseline`` -> returns a real ``PersonalBaseline`` or ``None``
  (missing-calibration case).

The *real* methodology configuration is used via the module's own
``load_methodology_config`` (not patched) so the asserted ``versions`` /
``config_hash`` are the genuine bundled values.

``process_multimodal_interview`` is ``async``; each case runs it with
``asyncio.run``. All cases are deterministic (no randomness, no real I/O).

Assertion philosophy: we assert the layered SHAPE (``raw`` / ``processed`` /
``base_labels`` / ``integrated_labels`` / ``quality`` / ``versions`` /
``config_hash`` / ``status``) and the status *semantics* (complete / partial /
failed, paraverbal ``None`` for patient turns, nonverbal present for all turns),
not exact interpretive label strings, so the tests stay robust to threshold /
rule vocabulary changes.
"""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.models.medical_interview import MediaAssetKind
from app.multimodal import pipeline as pipeline_module
from app.multimodal.config_loader import ConfigError, load_methodology_config
from app.multimodal.schemas import NonverbalRawFeatures, ParaverbalRawFeatures


# ---------------------------------------------------------------------------
# Fake DB session
# ---------------------------------------------------------------------------


def _clause_literals(args) -> list:
    """Extract literal comparison values from SQLAlchemy ``==`` filter clauses.

    ``_ready_asset`` filters media assets by ``kind`` and ``status`` using
    ``Column == "value"`` expressions. A no-op ``filter`` would wrongly return an
    asset of the wrong kind, so we introspect the right-hand literal of each
    clause (``clause.right.value``) and use them to constrain the fake rows. Any
    clause we cannot introspect is simply ignored (best-effort match).
    """
    literals: list = []
    for clause in args:
        right = getattr(clause, "right", None)
        value = getattr(right, "value", None) if right is not None else None
        if value is not None:
            literals.append(value)
    return literals


class _FakeQuery:
    """Minimal chainable query stub.

    ``.order_by(...)`` is a no-op. ``.filter(...)`` is a no-op for the model
    tables that the pipeline looks up by id (recording / interview / turns), but
    for media assets it constrains the rows by the literal ``kind`` / ``status``
    values in the clauses so ``_ready_asset`` returns the correct asset (or
    ``None`` when the requested kind is absent). ``.first()`` / ``.all()`` return
    the (possibly filtered) rows.
    """

    def __init__(self, rows: list, *, filter_by_literals: bool = False):
        self._rows = list(rows)
        self._filter_by_literals = filter_by_literals

    def filter(self, *args, **kwargs) -> "_FakeQuery":
        if not self._filter_by_literals:
            return self
        literals = _clause_literals(args)
        rows = [
            row
            for row in self._rows
            if all(
                (getattr(row, "kind", None) == literal)
                or (getattr(row, "status", None) == literal)
                or (getattr(row, "recording_id", None) == literal)
                for literal in literals
            )
        ]
        return _FakeQuery(rows, filter_by_literals=True)

    def order_by(self, *args, **kwargs) -> "_FakeQuery":
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self) -> list:
        return list(self._rows)


class _FakeSession:
    """In-memory stand-in for a SQLAlchemy Session.

    ``.query(Model)`` dispatches by ORM model class to the matching stub rows.
    Commits are counted so persistence tests can assert the batched commit ran.
    """

    def __init__(self, *, recording, interview, turns, assets):
        self._by_model = {
            pipeline_module.InterviewRecordingDB: [recording] if recording else [],
            pipeline_module.MedicalInterviewDB: [interview] if interview else [],
            pipeline_module.InterviewTurnDB: list(turns),
            pipeline_module.InterviewMediaAssetDB: list(assets),
        }
        self.commit_count = 0
        self.rollback_count = 0
        self.closed = False

    def query(self, model) -> _FakeQuery:
        rows = self._by_model.get(model, [])
        # Media-asset lookups must honour the kind/status filter so an absent
        # asset kind resolves to None (partial-audio / partial-video cases).
        filter_by_literals = model is pipeline_module.InterviewMediaAssetDB
        return _FakeQuery(rows, filter_by_literals=filter_by_literals)

    def commit(self) -> None:
        self.commit_count += 1

    def rollback(self) -> None:
        self.rollback_count += 1

    def close(self) -> None:
        self.closed = True


# ---------------------------------------------------------------------------
# Stub domain objects
# ---------------------------------------------------------------------------


def _make_turn(turn_id: str, speaker: str, sequence: int, start_ms: int, end_ms: int):
    """Build an InterviewTurnDB-like stub.

    ``paraverbal`` / ``nonverbal_features`` start unset and are the columns the
    pipeline writes into; ``SimpleNamespace`` lets the pipeline assign them.
    """
    return SimpleNamespace(
        id=turn_id,
        speaker=speaker,
        sequence=sequence,
        start_ms=start_ms,
        end_ms=end_ms,
        transcript="hello there how are you feeling today",
        medical_interview_id=1,
        paraverbal=None,
        nonverbal_features=None,
    )


def _make_recording(recording_id: str = "rec-1", interview_id: int = 1):
    return SimpleNamespace(
        id=recording_id,
        medical_interview_id=interview_id,
        capture_config={},
    )


def _make_interview(interview_id: int = 1):
    return SimpleNamespace(id=interview_id, interview_metadata={})


def _make_asset(kind: str, recording_id: str = "rec-1"):
    return SimpleNamespace(
        recording_id=recording_id,
        kind=kind,
        status="ready",
        storage_key=f"key-{kind}",
    )


def _baseline() -> pipeline_module.PersonalBaseline:
    """A realistic personal baseline (F0 in semitones, never Hz)."""
    return pipeline_module.PersonalBaseline(
        baseline_f0_semitones=-9.0,
        baseline_loudness=0.35,
        neutral_head_yaw=0.0,
        neutral_head_pitch=0.0,
        neutral_head_roll=0.0,
        neutral_gaze_yaw=0.0,
        neutral_gaze_pitch=0.0,
    )


# ---------------------------------------------------------------------------
# Raw-feature factories (returned by the patched extractors)
# ---------------------------------------------------------------------------


def _paraverbal_raw(turn_duration_ms: int = 4000) -> ParaverbalRawFeatures:
    """A usable raw paraverbal feature set for one student turn.

    Provides enough voiced signal, a word count, F0/loudness sample arrays (F0 in
    semitones), and a couple of pause segments so preprocessing derives real
    numbers. ``audio_quality`` is a plain dict as the extractor emits.
    """
    return ParaverbalRawFeatures(
        word_count=8,
        voiced_duration_ms=3200,
        f0_samples_semitones=[-9.0, -8.0, -7.5, -8.5, -9.5, -7.0, -8.0, -9.0],
        loudness_samples=[0.30, 0.35, 0.40, 0.38, 0.33, 0.36, 0.31, 0.34],
        pause_segments_ms=[300.0, 450.0],
        turn_duration_ms=turn_duration_ms,
        extractor={"name": "opensmile", "version": "test"},
        audio_quality={"snr_db": 25.0, "issues": []},
    )


def _nonverbal_payload(conversation_speaker: str, turn_duration_ms: int = 4000) -> dict:
    """The raw OpenFace 3.0 per-turn payload shape: NonverbalRawFeatures dump + context.

    Matches ``analyze_openface_student_turn_videos`` output: a
    ``NonverbalRawFeatures.model_dump()`` plus an ``observationContext`` block.
    Enough frames are provided that preprocessing can run; features that depend on
    null methodology params (gaze tolerance, AU12 threshold, nod params) will be
    reported unavailable-with-reason, which is the expected behaviour and still
    leaves the nonverbal layer usable.
    """
    timestamps = [0.0, 500.0, 1000.0, 1500.0, 2000.0, 2500.0, 3000.0, 3500.0]
    return {
        "face_score_samples": [0.98, 0.97, 0.99, 0.96, 0.98, 0.97, 0.99, 0.98],
        "gaze_yaw_samples": [0.01, 0.02, -0.01, 0.0, 0.03, -0.02, 0.01, 0.0],
        "gaze_pitch_samples": [0.0, -0.01, 0.02, 0.01, -0.02, 0.0, 0.01, -0.01],
        "au12_samples": [0.1, 0.2, 0.5, 0.6, 0.3, 0.4, 0.2, 0.1],
        "head_pitch_samples": [1.0, -1.0, 2.0, -2.0, 1.5, -1.5, 1.0, -1.0],
        "head_yaw_samples": [0.0, 0.5, -0.5, 0.0, 0.5, -0.5, 0.0, 0.0],
        "head_roll_samples": [0.0, 0.1, -0.1, 0.0, 0.1, -0.1, 0.0, 0.0],
        "frame_timestamps_ms": timestamps,
        "sample_fps": 2.0,
        "turn_duration_ms": turn_duration_ms,
        "extractor": {"name": "openface", "version": "test"},
        "video_quality": {"detected_frames": 8, "issues": []},
        "observationContext": {
            "observedParticipant": "student",
            "conversationSpeaker": conversation_speaker,
        },
    }


# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------


class _PipelineHarness:
    """Sets up patches for one pipeline run and captures the fake session.

    Callers customize behaviour by passing extractor return values / side effects
    and the baseline. ``run()`` executes the (async) pipeline to completion.
    """

    def __init__(
        self,
        *,
        turns,
        assets,
        paraverbal_return=None,
        paraverbal_side_effect=None,
        nonverbal_return=None,
        nonverbal_side_effect=None,
        baseline=None,
    ):
        self.recording = _make_recording()
        self.interview = _make_interview()
        self.session = _FakeSession(
            recording=self.recording,
            interview=self.interview,
            turns=turns,
            assets=assets,
        )
        self._paraverbal_return = paraverbal_return or {}
        self._paraverbal_side_effect = paraverbal_side_effect
        self._nonverbal_return = nonverbal_return or {}
        self._nonverbal_side_effect = nonverbal_side_effect
        self._baseline = baseline

    def run(self) -> None:
        storage = SimpleNamespace(resolve=lambda key: f"/tmp/{key}")

        def fake_paraverbal(audio_path, windows, **kwargs):
            if self._paraverbal_side_effect is not None:
                raise self._paraverbal_side_effect
            return dict(self._paraverbal_return)

        def fake_nonverbal(video_path, **kwargs):
            if self._nonverbal_side_effect is not None:
                raise self._nonverbal_side_effect
            return dict(self._nonverbal_return)

        def fake_build(payload, window, **kwargs):
            raw = {key: value for key, value in payload.items() if key != "observationContext"}
            return NonverbalRawFeatures.model_validate(raw)

        with patch.object(pipeline_module, "SessionLocal", return_value=self.session), \
                patch.object(pipeline_module, "get_media_storage", return_value=storage), \
                patch.object(pipeline_module, "analyze_student_turns", side_effect=fake_paraverbal), \
                patch.object(
                    pipeline_module,
                    "extract_nonverbal_video_observations",
                    side_effect=fake_nonverbal,
                ), \
                patch.object(
                    pipeline_module,
                    "segment_nonverbal_observations_by_turn",
                    side_effect=lambda observations, windows: observations,
                ), \
                patch.object(pipeline_module, "build_turn_raw_features", side_effect=fake_build), \
                patch.object(
                    pipeline_module, "read_personal_baseline", return_value=self._baseline
                ):
            asyncio.run(
                pipeline_module.process_multimodal_interview(
                    self.interview.id, self.recording.id
                )
            )

    def observation_processing(self) -> dict:
        """The final observation_processing block written into capture_config."""
        return self.recording.capture_config.get("observation_processing", {})


def _default_turns():
    """A deterministic conversation: 3 student turns interleaved with 2 patient turns."""
    return [
        _make_turn("t1", "student", 1, 0, 4000),
        _make_turn("t2", "patient", 2, 4000, 8000),
        _make_turn("t3", "student", 3, 8000, 12000),
        _make_turn("t4", "patient", 4, 12000, 16000),
        _make_turn("t5", "student", 5, 16000, 20000),
    ]


def _all_assets():
    return [
        _make_asset(MediaAssetKind.STUDENT_AUDIO.value),
        _make_asset(MediaAssetKind.STUDENT_VIDEO.value),
    ]


def _paraverbal_for(student_turn_ids) -> dict:
    return {turn_id: _paraverbal_raw() for turn_id in student_turn_ids}


def _nonverbal_for(turns) -> dict:
    return {
        turn.id: _nonverbal_payload(turn.speaker)
        for turn in turns
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class MultimodalPipelineTests(unittest.TestCase):
    """End-to-end behavioural tests for ``process_multimodal_interview``."""

    def setUp(self) -> None:
        # Real bundled config; asserted versions/config_hash come from here.
        self.config = load_methodology_config()

    # --- Happy path --------------------------------------------------------

    def test_happy_path_sets_layers_and_completes(self):
        """Both extractors usable + baseline present -> layered results persisted.

        Asserts the layered SHAPE and status semantics: each student turn has a
        paraverbal layer with all stage keys and status ``ok``; patient turns have
        no paraverbal layer; every turn has a nonverbal layer; and the final
        observation_processing status is ``complete`` (no gaps) OR ``partial`` if a
        session guard trips. Because our config's session-relative families feed
        through the two-pass guard, we assert the status is one of the usable
        terminal states and never ``failed`` / ``unavailable``.
        """
        turns = _default_turns()
        student_ids = [t.id for t in turns if t.speaker == "student"]
        harness = _PipelineHarness(
            turns=turns,
            assets=_all_assets(),
            paraverbal_return=_paraverbal_for(student_ids),
            nonverbal_return=_nonverbal_for(turns),
            baseline=_baseline(),
        )
        harness.run()

        by_id = {t.id: t for t in turns}
        # Student turns: paraverbal layer present with full layered shape + ok.
        for turn_id in student_ids:
            para = by_id[turn_id].paraverbal
            self.assertIsNotNone(para, f"student turn {turn_id} missing paraverbal")
            for key in (
                "raw",
                "processed",
                "base_labels",
                "integrated_labels",
                "quality",
                "versions",
                "config_hash",
                "status",
            ):
                self.assertIn(key, para)
            self.assertEqual(para["status"], "ok")
            self.assertIsNotNone(para["raw"])
            self.assertIsNotNone(para["processed"])
            self.assertIsNotNone(para["integrated_labels"])

        # Patient turns: paraverbal is None (never fabricated), nonverbal present.
        for turn in turns:
            if turn.speaker == "patient":
                self.assertIsNone(turn.paraverbal)
            self.assertIsNotNone(
                turn.nonverbal_features, f"turn {turn.id} missing nonverbal"
            )
            self.assertEqual(turn.nonverbal_features["status"], "ok")
            self.assertEqual(
                turn.nonverbal_features["quality"]["feature_reasons"]["visual_alignment_ratio"],
                "gaze_calibration_pending",
            )
            self.assertEqual(
                turn.nonverbal_features["base_labels"]["visual_orientation"]
                ["visual_alignment_ratio"]["reason"],
                "gaze_calibration_pending",
            )
            self.assertIsNotNone(
                turn.nonverbal_features["processed"]["mean_smile_activation"]
            )

        status = harness.observation_processing().get("status")
        self.assertIn(status, {"complete", "partial"})
        self.assertNotIn(status, {"failed", "unavailable"})

    # --- Partial audio -----------------------------------------------------

    def test_partial_audio_missing_asset_marks_partial(self):
        """No student-audio asset (video ok) -> paraverbal unavailable, partial run.

        Paraverbal layers on student turns are unavailable-with-reason, nonverbal
        layers are ok, and the overall status is ``partial`` (not failed).
        """
        turns = _default_turns()
        harness = _PipelineHarness(
            turns=turns,
            assets=[_make_asset(MediaAssetKind.STUDENT_VIDEO.value)],
            paraverbal_return={},  # extractor never reached; no audio asset
            nonverbal_return=_nonverbal_for(turns),
            baseline=_baseline(),
        )
        harness.run()

        for turn in turns:
            if turn.speaker == "student":
                self.assertIsNotNone(turn.paraverbal)
                self.assertEqual(turn.paraverbal["status"], "unavailable")
                self.assertIsNotNone(turn.paraverbal["reason"])
                self.assertIsNone(turn.paraverbal["processed"])
            self.assertIsNotNone(turn.nonverbal_features)
            self.assertEqual(turn.nonverbal_features["status"], "ok")

        self.assertEqual(harness.observation_processing().get("status"), "partial")

    # --- Partial video -----------------------------------------------------

    def test_partial_video_missing_asset_marks_partial(self):
        """No student-video asset (audio ok) -> nonverbal unavailable, partial run."""
        turns = _default_turns()
        student_ids = [t.id for t in turns if t.speaker == "student"]
        harness = _PipelineHarness(
            turns=turns,
            assets=[_make_asset(MediaAssetKind.STUDENT_AUDIO.value)],
            paraverbal_return=_paraverbal_for(student_ids),
            nonverbal_return={},  # extractor never reached; no video asset
            baseline=_baseline(),
        )
        harness.run()

        for turn in turns:
            self.assertIsNotNone(turn.nonverbal_features)
            self.assertEqual(turn.nonverbal_features["status"], "unavailable")
            self.assertIsNotNone(turn.nonverbal_features["reason"])
            if turn.speaker == "student":
                self.assertEqual(turn.paraverbal["status"], "ok")

        self.assertEqual(harness.observation_processing().get("status"), "partial")

    # --- Missing calibration ----------------------------------------------

    def test_missing_calibration_still_completes_or_partial(self):
        """No personal baseline -> baseline-dependent features unavailable, not failed.

        With ``read_personal_baseline`` returning ``None``, the pipeline still runs
        both modalities and produces layered results; the run is a usable terminal
        state (complete/partial), never failed. Baseline-dependent base labels
        (e.g. ``relative_pitch_shift_st``) surface a missing_calibration reason,
        but the layer status stays ``ok`` because other features are derivable.
        """
        turns = _default_turns()
        student_ids = [t.id for t in turns if t.speaker == "student"]
        harness = _PipelineHarness(
            turns=turns,
            assets=_all_assets(),
            paraverbal_return=_paraverbal_for(student_ids),
            nonverbal_return=_nonverbal_for(turns),
            baseline=None,
        )
        harness.run()

        # Layers still produced for both modalities.
        for turn in turns:
            self.assertIsNotNone(turn.nonverbal_features)
            if turn.speaker == "student":
                self.assertIsNotNone(turn.paraverbal)
                self.assertEqual(turn.paraverbal["status"], "ok")

        status = harness.observation_processing().get("status")
        self.assertIn(status, {"complete", "partial"})
        self.assertNotIn(status, {"failed", "unavailable"})

    # --- Extraction failure in one modality --------------------------------

    def test_paraverbal_extractor_exception_yields_partial(self):
        """Paraverbal extractor raising -> nonverbal still processed, run not failed.

        A single-modality extractor exception must be caught inside the pipeline
        (Requirement 24.2): paraverbal layers become unavailable, nonverbal layers
        are ok, the overall status is ``partial``, and the coroutine does not
        crash / propagate.
        """
        turns = _default_turns()
        harness = _PipelineHarness(
            turns=turns,
            assets=_all_assets(),
            paraverbal_side_effect=RuntimeError("opensmile boom"),
            nonverbal_return=_nonverbal_for(turns),
            baseline=_baseline(),
        )
        harness.run()  # must not raise

        for turn in turns:
            self.assertIsNotNone(turn.nonverbal_features)
            self.assertEqual(turn.nonverbal_features["status"], "ok")
            if turn.speaker == "student":
                self.assertEqual(turn.paraverbal["status"], "unavailable")

        status = harness.observation_processing().get("status")
        self.assertEqual(status, "partial")
        self.assertNotEqual(status, "failed")

    # --- DB persistence ----------------------------------------------------

    def test_db_persistence_assigns_columns_and_commits(self):
        """Turn columns are assigned and the batched commit runs.

        Asserts ``turn.paraverbal`` / ``turn.nonverbal_features`` were assigned and
        that at least one ``db.commit()`` happened (the pipeline commits per stage
        transition and once for the batched persistence, so the count is > 1).
        """
        turns = _default_turns()
        student_ids = [t.id for t in turns if t.speaker == "student"]
        harness = _PipelineHarness(
            turns=turns,
            assets=_all_assets(),
            paraverbal_return=_paraverbal_for(student_ids),
            nonverbal_return=_nonverbal_for(turns),
            baseline=_baseline(),
        )
        harness.run()

        for turn in turns:
            # nonverbal is present for all turns; paraverbal for student turns.
            self.assertIsNotNone(turn.nonverbal_features)
            if turn.speaker == "student":
                self.assertIsNotNone(turn.paraverbal)

        # The batched persistence commit ran alongside the per-stage commits.
        self.assertGreater(harness.session.commit_count, 1)
        self.assertTrue(harness.session.closed)

    # --- Version persistence ----------------------------------------------

    def test_version_persistence_matches_loaded_config(self):
        """Every persisted layer carries versions + config_hash matching the config.

        The layered dicts must carry the ``processing`` / ``thresholds`` /
        ``label_rules`` versions and the deterministic ``config_hash`` from the
        loaded methodology config (Requirement 6.1-6.3).
        """
        turns = _default_turns()
        student_ids = [t.id for t in turns if t.speaker == "student"]
        harness = _PipelineHarness(
            turns=turns,
            assets=_all_assets(),
            paraverbal_return=_paraverbal_for(student_ids),
            nonverbal_return=_nonverbal_for(turns),
            baseline=_baseline(),
        )
        harness.run()

        expected_versions = self.config.versions.model_dump()
        expected_hash = self.config.config_hash

        for turn in turns:
            layers = [turn.nonverbal_features]
            if turn.speaker == "student":
                layers.append(turn.paraverbal)
            for layer in layers:
                self.assertIsNotNone(layer)
                self.assertEqual(layer["versions"], expected_versions)
                self.assertEqual(layer["config_hash"], expected_hash)
                # Versions expose the two methodology config files.
                self.assertIn("thresholds", layer["versions"])
                self.assertIn("label_rules", layer["versions"])

    # --- Whole-run failure (optional) --------------------------------------

    def test_config_error_marks_failed_without_propagating(self):
        """An unexpected ConfigError -> failed status, coroutine does not propagate.

        Forcing ``load_methodology_config`` to raise ``ConfigError`` exercises the
        ``_mark_failed`` path: the observation_processing status becomes ``failed``
        and the (async) coroutine completes without raising to the caller.
        """
        turns = _default_turns()
        harness = _PipelineHarness(
            turns=turns,
            assets=_all_assets(),
            paraverbal_return={},
            nonverbal_return={},
            baseline=_baseline(),
        )

        storage = SimpleNamespace(resolve=lambda key: f"/tmp/{key}")
        with patch.object(pipeline_module, "SessionLocal", return_value=harness.session), \
                patch.object(pipeline_module, "get_media_storage", return_value=storage), \
                patch.object(
                    pipeline_module,
                    "load_methodology_config",
                    side_effect=ConfigError("bad config file"),
                ):
            # Must not raise despite the ConfigError inside the pipeline.
            asyncio.run(
                pipeline_module.process_multimodal_interview(
                    harness.interview.id, harness.recording.id
                )
            )

        self.assertEqual(harness.observation_processing().get("status"), "failed")
        self.assertGreaterEqual(harness.session.rollback_count, 1)


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    unittest.main()
