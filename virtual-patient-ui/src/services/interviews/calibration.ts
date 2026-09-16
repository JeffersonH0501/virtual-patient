import {CalibrationResult, CompleteInterviewResponse, PersonalBaseline} from '../../types/interview';
import {transformToCamelCase, transformToSnakeCase} from '../../utils/apiTransform';
import {apiFetch} from '../../utils/apiFetch';
import {API_URL} from '../../utils/request';
import {getAuthHeaders} from '../auth/authHeaders';

export type CalibrationResultPayload = Omit<CalibrationResult, 'completedAt'>;

// Response of the backend baseline endpoint. When `status` is "unavailable" the
// baseline could not be derived (e.g. insufficient signal); the client must
// treat that as a non-blocking outcome and still allow saving the technical
// calibration.
export type CalibrationBaselineResponse = {
  status: 'ok' | 'unavailable';
  personalBaseline?: PersonalBaseline | null;
  reason?: string | null;
};

const requireInterview = async (response: Response): Promise<CompleteInterviewResponse> => {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || 'Interview calibration request failed');
  }
  return transformToCamelCase(await response.json()) as CompleteInterviewResponse;
};

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

// Derives the same numeric baseline without creating or mutating an interview.
// The backend uses temporary media only; the caller keeps the returned numbers
// in memory until the user explicitly starts the simulation.
export const deriveStandaloneCalibrationBaseline = async (
  media: {audio?: Blob | null; video?: Blob | null},
): Promise<CalibrationBaselineResponse> => {
  const form = new FormData();
  if (media.audio) form.append('audio', media.audio, 'calibration-audio');
  if (media.video) form.append('video', media.video, 'calibration-video');
  const response = await apiFetch(
    `${API_URL}/medical-interviews/calibration/baseline`,
    {method: 'POST', headers: getAuthHeaders(), body: form},
  );
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || 'Calibration baseline request failed');
  }
  return transformToCamelCase(await response.json()) as CalibrationBaselineResponse;
};
