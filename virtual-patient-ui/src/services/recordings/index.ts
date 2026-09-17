import {getAuthHeaders} from '../auth/authHeaders';
import {transformToCamelCase} from '../../utils/apiTransform';
import {API_URL} from '../../utils/request';
import {
  CapturedMedia,
  InterviewRecap,
  RecapTurn,
  RecordingStatus,
} from '../../types/recording';
import {
  normalizeNonverbalObservation,
  normalizeParaverbalObservation,
} from '../recap/normalizeObservation';

type RecordingState = {
  interviewId: number;
  recordingId: string;
  recordingStatus: RecordingStatus;
  durationMs?: number | null;
};

const requireOk = async (response: Response): Promise<Response> => {
  if (response.ok) return response;
  const body = await response.json().catch(() => ({}));
  throw new Error(body.detail || 'Interview recording request failed');
};

export const startInterviewRecording = async (
  interviewId: number,
  startedAt: string,
  captureConfig: Record<string, unknown>,
): Promise<RecordingState> => {
  const response = await requireOk(await fetch(
    `${API_URL}/medical-interviews/${interviewId}/recording/start`,
    {
      method: 'POST',
      headers: {'Content-Type': 'application/json', ...getAuthHeaders()},
      body: JSON.stringify({started_at: startedAt, capture_config: captureConfig}),
    },
  ));
  return transformToCamelCase(await response.json()) as RecordingState;
};

export const saveInterviewTurn = async (
  interviewId: number,
  messageId: number,
  payload: {
    speaker: 'student' | 'patient';
    sequence: number;
    startMs: number;
    endMs: number;
    transcript: string;
    inputSource: string;
    timingSource: string;
    timingQuality: 'measured' | 'provisional' | 'estimated';
  },
): Promise<void> => {
  await requireOk(await fetch(
    `${API_URL}/medical-interviews/${interviewId}/recording/turns/${messageId}`,
    {
      method: 'PUT',
      headers: {'Content-Type': 'application/json', ...getAuthHeaders()},
      body: JSON.stringify({
        speaker: payload.speaker,
        sequence: payload.sequence,
        start_ms: payload.startMs,
        end_ms: payload.endMs,
        transcript: payload.transcript,
        input_source: payload.inputSource,
        timing_source: payload.timingSource,
        timing_quality: payload.timingQuality,
      }),
    },
  ));
};

export const finalizeInterviewRecording = (
  interviewId: number,
  captured: CapturedMedia,
  onProgress?: (progress: number) => void,
): Promise<RecordingState> => new Promise((resolve, reject) => {
  const form = new FormData();
  form.append('duration_ms', String(captured.durationMs));
  form.append('source_durations', JSON.stringify(captured.sourceDurations));
  form.append('capture_config', JSON.stringify(captured.captureConfig));
  Object.entries(captured.files).forEach(([kind, file]) => form.append(kind, file));

  const request = new XMLHttpRequest();
  request.open('POST', `${API_URL}/medical-interviews/${interviewId}/recording/finalize`);
  Object.entries(getAuthHeaders()).forEach(([name, value]) => request.setRequestHeader(name, value));
  request.upload.onprogress = (event) => {
    if (event.lengthComputable) onProgress?.(event.loaded / event.total);
  };
  request.onerror = () => reject(new Error('Interview recording upload failed'));
  request.onload = () => {
    if (request.status < 200 || request.status >= 300) {
      const message = (() => {
        try {
 return JSON.parse(request.responseText).detail;
} catch {
 return null;
}
      })();
      console.error('Interview recording finalization failed', {
        interviewId,
        status: request.status,
        response: message || 'No response detail',
      });
      reject(new Error(message || 'Interview recording upload failed'));
      return;
    }
    console.info('Interview recording finalized', {
      interviewId,
      status: request.status,
      durationMs: captured.durationMs,
      assetKinds: Object.keys(captured.files),
    });
    resolve(transformToCamelCase(JSON.parse(request.responseText)) as RecordingState);
  };
  request.send(form);
});

export const markInterviewRecordingUnavailable = async (
  interviewId: number,
  failureCode: string,
  durationMs?: number,
): Promise<void> => {
  await requireOk(await fetch(
    `${API_URL}/medical-interviews/${interviewId}/recording/unavailable`,
    {
      method: 'POST',
      headers: {'Content-Type': 'application/json', ...getAuthHeaders()},
      body: JSON.stringify({failure_code: failureCode, duration_ms: durationMs}),
    },
  ));
};

// Route every turn's observations through the frontend compatibility adapter so
// both the backend-normalized layered shape and any raw legacy flat payload that
// did not pass through the backend normalizer reach the recap UI in the same
// layered read view (Requirements 22.2, 23.2). This is read-time only and
// non-destructive: layered payloads pass through unchanged.
const normalizeRecapTurn = (turn: RecapTurn): RecapTurn => ({
  ...turn,
  paraverbal: normalizeParaverbalObservation(turn.paraverbal),
  nonverbalFeatures: normalizeNonverbalObservation(turn.nonverbalFeatures),
});

export const getInterviewRecap = async (interviewId: number): Promise<InterviewRecap> => {
  const response = await requireOk(await fetch(
    `${API_URL}/medical-interviews/${interviewId}/recap`,
    {headers: getAuthHeaders()},
  ));
  const recap = transformToCamelCase(await response.json()) as InterviewRecap;
  return {
    ...recap,
    turns: Array.isArray(recap.turns) ? recap.turns.map(normalizeRecapTurn) : recap.turns,
  };
};

/**
 * Trigger a full re-analysis (multimodal pipeline first, then the final text
 * evaluation) for a completed interview. The backend runs the work as a
 * background task and reports progress through the recap's
 * ``observationProcessing`` status, so callers poll ``getInterviewRecap`` until
 * that status becomes terminal.
 */
export const reprocessInterviewRecording = async (
  interviewId: number,
): Promise<RecordingState> => {
  const response = await requireOk(await fetch(
    `${API_URL}/medical-interviews/${interviewId}/recording/reprocess`,
    {method: 'POST', headers: getAuthHeaders()},
  ));
  return transformToCamelCase(await response.json()) as RecordingState;
};

export const resolveRecordingSource = (source?: string | null): string | null => {
  if (!source) return null;
  return source.startsWith('http') ? source : `${API_URL}${source}`;
};
