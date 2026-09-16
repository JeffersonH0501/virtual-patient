export type RecordingStatus =
  | 'idle'
  | 'recording'
  | 'paused'
  | 'finalizing'
  | 'ready'
  | 'partial'
  | 'unavailable'
  | 'failed';

export type RecordingAssetKind =
  | 'student_audio'
  | 'student_video'
  | 'patient_audio'
  | 'patient_video';

export type RecapTurn = {
  turnId: string;
  messageId?: number | null;
  speaker: 'student' | 'patient';
  startMs?: number | null;
  endMs?: number | null;
  transcript: string;
  inputSource: string;
  timingSource: string;
  timingQuality: string;
  paraverbal?: ParaverbalObservation | null;
  nonverbalFeatures?: NonverbalObservation | null;
};

// The backend recap endpoint returns, for each turn's `paraverbal` and
// `nonverbal_features`, a NORMALIZED read view produced by
// `app/multimodal/legacy_adapter.normalize_observation`. The API serializes
// snake_case JSON which the recordings service converts recursively to
// camelCase (see utils/apiTransform). The types below model that camelCased
// read view. Two shapes coexist behind a discriminated union on `schema`:
//   - "layered": the new pipeline output with staged layers.
//   - "legacy":  a pre-refactor flat payload wrapped into the layered shape by
//     the backend adapter (raw/baseLabels null, only the temporal integrated
//     label may carry a genuine value, versions/configHash null).
// The union keeps legacy payloads renderable without a destructive migration
// (Requirements 22.1, 22.3, 23.1). Backend `_without_none` strips keys whose
// value is null, so every layered field is modelled as optional.

export type ObservationSchema = 'layered' | 'legacy';

// Outcome status shared by family labels and modality layers. Mirrors the
// backend `OutcomeStatus` enum; kept as a widened string so an unforeseen
// backend value never breaks rendering.
export type ObservationStatus =
  | 'ok'
  | 'unavailable'
  | 'insufficient_reference_data'
  | (string & {});

// One integrated label for a family. `value` is present only when `status` is
// "ok"; otherwise it is absent/null and `reason` explains the gap. `evidence`
// is a free-form record whose contents differ by family and origin.
export type FamilyLabel = {
  status?: ObservationStatus;
  value?: string | null;
  reason?: string | null;
  evidence?: Record<string, unknown>;
};

// Derived paraverbal metrics (the `processed` layer). Field names match the
// camelCased backend derivation formulas. All optional: a metric that could
// not be derived is absent rather than a fabricated number.
export type ParaverbalProcessed = {
  speechRateWpm?: number | null;
  articulationRateWpm?: number | null;
  pauseCount?: number | null;
  totalPauseDurationMs?: number | null;
  medianPauseDurationMs?: number | null;
  pauseFrequencyPerMin?: number | null;
  pauseTimeRatio?: number | null;
  medianLoudness?: number | null;
  f0MedianSemitones?: number | null;
  f0P20P80RangeSemitones?: number | null;
  loudnessP20P80Range?: number | null;
  relativePitchShiftSt?: number | null;
};

// Exactly one integrated label per paraverbal family.
export type ParaverbalIntegratedLabels = {
  temporal?: FamilyLabel;
  prosodicLevel?: FamilyLabel;
  prosodicModulation?: FamilyLabel;
};

// Per-feature base (initial) labels grouped by family. Each family maps a
// camelCased feature key (e.g. `speechRateWpm`) to its per-feature FamilyLabel
// from the threshold stage. These are the "initial labels" shown between the
// base features and the integrated label. Optional because a legacy payload
// carries `baseLabels: null`.
export type ParaverbalBaseLabels = {
  temporal?: Record<string, FamilyLabel>;
  prosodicLevel?: Record<string, FamilyLabel>;
  prosodicModulation?: Record<string, FamilyLabel>;
};

export type ParaverbalObservation = {
  schema?: ObservationSchema;
  modality?: 'paraverbal';
  raw?: Record<string, unknown> | null;
  processed?: ParaverbalProcessed;
  baseLabels?: ParaverbalBaseLabels | null;
  integratedLabels?: ParaverbalIntegratedLabels;
  quality?: {validRatio?: number | null; issues?: string[]; [key: string]: unknown};
  versions?: Record<string, string> | null;
  configHash?: string | null;
  status?: ObservationStatus;
  reason?: string | null;
  // Present only on normalized legacy payloads: the original interpretability
  // block, kept so a detail view can surface the legacy temporal reasoning.
  legacyInterpretability?: Record<string, unknown> | null;
  // Interaction context ("speaking" | "listening") when the backend resolved it.
  context?: string | null;
};

// Derived nonverbal metrics (the `processed` layer).
export type NonverbalProcessed = {
  visualAlignmentRatio?: number | null;
  medianVisualAlignmentDwellMs?: number | null;
  nodCount?: number | null;
  nodRateMin?: number | null;
  smileActivityRatio?: number | null;
  meanSmileActivation?: number | null;
  context?: string | null;
};

// Exactly one integrated label per nonverbal family.
export type NonverbalIntegratedLabels = {
  visualOrientation?: FamilyLabel;
  headGesturalFeedback?: FamilyLabel;
  facialExpressivity?: FamilyLabel;
};

// Per-feature base (initial) labels grouped by nonverbal family.
export type NonverbalBaseLabels = {
  visualOrientation?: Record<string, FamilyLabel>;
  headGesturalFeedback?: Record<string, FamilyLabel>;
  facialExpressivity?: Record<string, FamilyLabel>;
};

export type NonverbalObservation = {
  schema?: ObservationSchema;
  modality?: 'nonverbal';
  raw?: Record<string, unknown> | null;
  processed?: NonverbalProcessed;
  baseLabels?: NonverbalBaseLabels | null;
  integratedLabels?: NonverbalIntegratedLabels;
  quality?: {sampledFrameCount?: number; validFrameCount?: number; issues?: string[]; [key: string]: unknown};
  versions?: Record<string, string> | null;
  configHash?: string | null;
  status?: ObservationStatus;
  reason?: string | null;
  context?: string | null;
};

export type InterviewRecap = {
  interviewId: number;
  recordingStatus: RecordingStatus;
  durationMs?: number | null;
  observationProcessing?: {
    status?: 'queued' | 'processing' | 'complete' | 'partial' | 'failed' | 'unavailable';
    stage?: string;
    expected?: number;
    available?: number;
  };
  studentAudioSource?: string | null;
  studentVideoSource?: string | null;
  patientAudioSource?: string | null;
  patientVideoSource?: string | null;
  turns: RecapTurn[];
};

export type CapturedMedia = {
  durationMs: number;
  files: Record<RecordingAssetKind, File>;
  sourceDurations: Record<RecordingAssetKind, number>;
  captureConfig: Record<string, unknown>;
};

export type SpeechTiming = {
  startedAt: number;
  endedAt: number;
  inputSource?: 'browser_speech' | 'azure_openai_stt';
  timingSource?: 'browser_speech_events' | 'client_audio_activity';
};
