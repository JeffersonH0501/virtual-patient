import {CalibrationResult, CompleteInterviewResponse, PersonalBaseline} from '../../types/interview';
import {transformToCamelCase, transformToSnakeCase} from '../../utils/apiTransform';
import {apiFetch} from '../../utils/apiFetch';
import {API_URL} from '../../utils/request';
import {getAuthHeaders} from '../auth/authHeaders';

// The calibration result the client keeps in memory as a draft after temporary
// processing. It mirrors the backend ``CalibrationProcessResponse`` and, when
// passed, carries the profile (including the gaze affine matrix) and the numeric
// personal baseline. Nothing is persisted server-side until the user starts an
// interview and the draft is saved into ``interview_metadata.calibration``.
export type CalibrationDraft = {
  status: 'passed' | 'failed';
  failureReason: string | null;
  calibrationVersion: string;
  profile: Record<string, unknown> | null;
  quality: Record<string, unknown> | null;
  personalBaseline: PersonalBaseline | null;
};

// The payload persisted into an interview before it starts (camelCased; the
// service snake-cases it for the API). It omits the client-only completion time,
// which the backend stamps on save.
export type CalibrationResultPayload = Omit<CalibrationResult, 'completedAt'>;

// Runs the temporary calibration processing. The backend writes the upload to a
// temporary file, runs the isolated video/audio workers, always deletes the
// media, and returns the result. No database row or permanent media is created.
export const processTemporaryCalibration = async (
  media: Blob,
  durationMs: number,
  metadata: Record<string, unknown>,
): Promise<CalibrationDraft> => {
  const form = new FormData();
  form.append('video', media, 'multimodal-calibration.webm');
  form.append('duration_ms', String(Math.round(durationMs)));
  form.append('metadata_json', JSON.stringify(transformToSnakeCase(metadata)));
  const response = await apiFetch(`${API_URL}/calibration/process`, {
    method: 'POST', headers: getAuthHeaders(), body: form,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const error = new Error(body.detail || 'Calibration processing failed') as Error & {status?: number};
    error.status = response.status;
    throw error;
  }
  return transformToCamelCase(await response.json()) as CalibrationDraft;
};

const requireInterview = async (response: Response): Promise<CompleteInterviewResponse> => {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || 'Interview calibration request failed');
  }
  return transformToCamelCase(await response.json()) as CompleteInterviewResponse;
};

// Persists a passed calibration draft into an interview before it starts. The
// media is never sent; only the numeric result and profile are stored under
// ``interview_metadata.calibration``.
export const saveCalibrationResult = async (
  interviewId: number,
  result: CalibrationResultPayload,
): Promise<CompleteInterviewResponse> => requireInterview(await apiFetch(
  `${API_URL}/medical-interviews/${interviewId}/calibration`,
  {
    method: 'PUT',
    headers: {'Content-Type': 'application/json', ...getAuthHeaders()},
    body: JSON.stringify(transformToSnakeCase(result)),
  },
));

export const startInterview = async (
  interviewId: number,
): Promise<CompleteInterviewResponse> => requireInterview(await apiFetch(
  `${API_URL}/medical-interviews/${interviewId}/start`,
  {method: 'POST', headers: getAuthHeaders()},
));
