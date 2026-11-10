import {getAuthHeaders} from '../auth/authHeaders';
import {transformToCamelCase} from '../../utils/apiTransform';
import {API_URL} from '../../utils/request';
import {apiFetch} from '../../utils/apiFetch';
import {CaptureSyncError} from '../../recording/CaptureSyncError';
import {
  InterviewRecap,
  RecordingStatus,
} from '../../types/recording';

type RecordingState = {
  interviewId: number;
  recordingId: string;
  recordingStatus: RecordingStatus;
  durationMs?: number | null;
  preservationAccepted?: boolean;
};

const requireOk = async (response: Response): Promise<Response> => {
  if (response.ok) return response;
  const body = await response.json().catch(() => ({}));
  throw new CaptureSyncError(response.status, typeof body.detail === 'string' ? body.detail : body.detail?.code ?? 'capture_request_failed');
};


export const getInterviewRecap = async (interviewId: number, signal?: AbortSignal): Promise<InterviewRecap> => {
  const response = await requireOk(await apiFetch(
    `${API_URL}/medical-interviews/${interviewId}/recap`,
    {headers: getAuthHeaders(), signal},
  ));
  // The recap endpoint serves the single canonical layered observation schema;
  // the camelCase transform is the only read-time adaptation the UI needs.
  return transformToCamelCase(await response.json()) as InterviewRecap;
};

/**
 * Trigger full signal extraction and integrated labeling without LLM evaluation
 * for a completed interview. The backend runs the work as a
 * background task and reports progress through the recap's
 * ``observationProcessing`` status, so callers poll ``getInterviewRecap`` until
 * that status becomes terminal.
 */
export const reprocessInterviewRecording = async (
  interviewId: number,
): Promise<RecordingState> => {
  const response = await requireOk(await apiFetch(
    `${API_URL}/medical-interviews/${interviewId}/recording/reprocess`,
    {method: 'POST', headers: getAuthHeaders()},
  ));
  return transformToCamelCase(await response.json()) as RecordingState;
};

export const resolveRecordingSource = (source?: string | null): string | null => {
  if (!source) return null;
  return source.startsWith('http') ? source : `${API_URL}${source}`;
};

/** Evaluate existing integrated labels without extracting media features. */
export const regenerateInterviewEvaluation = async (interviewId: number): Promise<RecordingState> => {
  const response = await requireOk(await apiFetch(
    `${API_URL}/medical-interviews/${interviewId}/evaluation/regenerate`,
    {method: 'POST', headers: getAuthHeaders()},
  ));
  return transformToCamelCase(await response.json()) as RecordingState;
};
