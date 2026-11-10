import {CalibrationResult, CompleteInterviewResponse} from '../../types/interview';
import {transformToCamelCase, transformToSnakeCase} from '../../utils/apiTransform';
import {apiFetch} from '../../utils/apiFetch';
import {API_URL} from '../../utils/request';
import {getAuthHeaders} from '../auth/authHeaders';

// The payload persisted into an interview before it starts (camelCased; the
// service snake-cases it for the API). It omits the client-only completion time,
// which the backend stamps on save.
export type CalibrationResultPayload = Omit<CalibrationResult, 'completedAt'> & {attestations?: Record<string, string>};

export type CalibrationStage = 'gaze' | 'camera' | 'unified' | 'guided';
export type GuidedCheckDiagnostics = {
  processingTimeSeconds?: number;
  version: 'guided_checks_v1' | 'guided_checks_v2' | 'guided_checks_v4_orientation';
  diagnosticOnly: true;
  promptLabelsVerified: false;
  environment?: {deviceType: string; cameraPosition: string} | null;
  geometry?: {orientation: string} | null;
  phases: {kind: string; status: string; gazeValidRatio: number | null;
    gazeErrorMedian: number | null; smileActivityRatio: number | null;
    faceValidRatio?: number; sampleCount?: number; nodCount?: number | null; promptedNodCount?: number | null;
    nodEvaluableWindows?: number; nodWindowCoverage?: number; nodUnavailableReason?: string | null;
    meanSmileActivation?: number | null}[];
};
export type CalibrationStageResult = {
  stage: CalibrationStage;
  status: 'passed' | 'failed';
  failureReason: string | null;
  result: Record<string, unknown> | null;
  attestation?: string | null;
};

export const warmUpCalibration = async (): Promise<void> => {
  const response = await apiFetch(`${API_URL}/calibration/warm-up`, {
    method: 'POST', headers: getAuthHeaders(),
  });
  if (!response.ok) throw new Error('Visual calibration warm-up failed');
};

export const processGazeTestFrame = async (media: Blob, attemptId: string, attestations: Record<string, string>, geometry: object, signal: AbortSignal): Promise<'inside' | 'outside' | 'indeterminate'> => {
  const form = new FormData();
  form.append('media', media, 'frame.jpg');
  form.append('attempt_id', attemptId);
  form.append('attestations_json', JSON.stringify(attestations));
  form.append('geometry_json', JSON.stringify(transformToSnakeCase(geometry)));
  const response = await apiFetch(`${API_URL}/calibration/gaze-test/frame`, {method: 'POST', headers: getAuthHeaders(), body: form, signal});
  if (!response.ok) throw Object.assign(new Error('Gaze test frame failed'), {status: response.status});
  const {state} = await response.json();
  return state === 'inside' || state === 'outside' ? state : 'indeterminate';
};

export const discardCalibrationDraft = async (interviewId: number): Promise<void> => {
  const response = await apiFetch(`${API_URL}/calibration/drafts/${interviewId}`, {
    method: 'DELETE', headers: getAuthHeaders(), keepalive: true, signal: AbortSignal.timeout(30_000),
  });
  if (!response.ok && response.status !== 404) {
    throw Object.assign(new Error('Calibration draft could not be discarded'), {status: response.status});
  }
};

export const discardResumeCalibration = async (interviewId: number, attemptId: string): Promise<void> => {
  const response = await apiFetch(`${API_URL}/calibration/resume/${interviewId}/${encodeURIComponent(attemptId)}`, {
    method: 'DELETE', headers: getAuthHeaders(), signal: AbortSignal.timeout(30_000),
  });
  if (!response.ok && response.status !== 404 && response.status !== 409) {
    throw new Error('Resume calibration could not be discarded');
  }
};

export const processCalibrationStage = async (
  stage: CalibrationStage,
  interviewId: number,
  media: Blob,
  durationMs: number,
  metadata: Record<string, unknown>,
  resumeAttemptId?: string,
): Promise<CalibrationStageResult> => {
  const form = new FormData();
  form.append('stage', stage);
  form.append('interview_id', String(interviewId));
  form.append('media', media, `${stage}-calibration.webm`);
  form.append('duration_ms', String(Math.round(durationMs)));
  form.append('metadata_json', JSON.stringify(transformToSnakeCase(metadata)));
  if (resumeAttemptId) form.append('resume_attempt_id', resumeAttemptId);
  const response = await apiFetch(`${API_URL}/calibration/process-stage`, {
    method: 'POST', headers: getAuthHeaders(), body: form, signal: AbortSignal.timeout(240_000),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw Object.assign(new Error(body.detail || 'Calibration checkpoint processing failed'), {status: response.status});
  }
  return transformToCamelCase(await response.json()) as CalibrationStageResult;
};

export const processNonverbalTest = async (
  stage: CalibrationStage, attemptId: string, media: Blob, durationMs: number,
  metadata: Record<string, unknown>,
): Promise<CalibrationStageResult> => {
  const form = new FormData();
  form.append('stage', stage);
  form.append('attempt_id', attemptId);
  form.append('media', media, `${stage}-nonverbal-test.webm`);
  form.append('duration_ms', String(Math.round(durationMs)));
  form.append('metadata_json', JSON.stringify(transformToSnakeCase(metadata)));
  const response = await apiFetch(`${API_URL}/calibration/nonverbal-test`, {
    method: 'POST', headers: getAuthHeaders(), body: form, signal: AbortSignal.timeout(240_000),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw Object.assign(new Error(body.detail || 'Nonverbal test processing failed'), {status: response.status});
  }
  return transformToCamelCase(await response.json()) as CalibrationStageResult;
};

const requireInterview = async (response: Response): Promise<CompleteInterviewResponse> => {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw Object.assign(new Error(body.detail || 'Interview calibration request failed'), {status: response.status});
  }
  return transformToCamelCase(await response.json()) as CompleteInterviewResponse;
};

// Persists a passed calibration draft into an interview before it starts. The
// media is never sent; only the numeric result and profile are stored under
// ``interview_metadata.calibration``.
export const saveCalibrationResult = async (
  interviewId: number,
  result: CalibrationResultPayload,
  resumeAttemptId?: string,
): Promise<CompleteInterviewResponse> => requireInterview(await apiFetch(
  `${API_URL}/medical-interviews/${interviewId}/calibration`,
  {
    method: 'PUT',
    signal: AbortSignal.timeout(30_000),
    headers: {'Content-Type': 'application/json', ...getAuthHeaders()},
    body: JSON.stringify(transformToSnakeCase({...result, resumeAttemptId})),
  },
));

export const startInterview = async (
  interviewId: number,
): Promise<CompleteInterviewResponse> => requireInterview(await apiFetch(
  `${API_URL}/medical-interviews/${interviewId}/start`,
  {method: 'POST', headers: getAuthHeaders(), signal: AbortSignal.timeout(30_000)},
));
