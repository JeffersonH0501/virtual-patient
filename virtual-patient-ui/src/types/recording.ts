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

export type ParaverbalObservation = {
  extractor?: {name: string; version: string; featureSet: string};
  wordCount?: number;
  voicedDurationMs?: number;
  speechRateWpm?: number | null;
  articulationRateWpm?: number | null;
  pauseCount?: number;
  totalPauseDurationMs?: number;
  medianPauseDurationMs?: number | null;
  pauseTimeRatio?: number | null;
  f0MedianSemitones?: number | null;
  f0P20P80RangeSemitones?: number | null;
  medianLoudness?: number | null;
  loudnessP20P80Range?: number | null;
  audioQuality?: {validRatio?: number | null; issues?: string[]};
  interpretability?: {
    acousticTemporal?: {
      labels?: {
        status?: string;
        values?: Record<string, string>;
      };
    };
  };
};

export type NonverbalObservation = {
  extractor?: {name: string; package?: string; version: string; sampleFps?: number};
  visualAlignmentRatio?: number | null;
  medianVisualAlignmentDwellMs?: number | null;
  nodCount?: number | null;
  nodRateMin?: number | null;
  smileActivityRatio?: number | null;
  meanSmileActivation?: number | null;
  videoValidRatio?: number | null;
  videoQuality?: {sampledFrameCount?: number; validFrameCount?: number; issues?: string[]};
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
