import {apiFetch} from '../../utils/apiFetch';
import {API_URL} from '../../utils/request';
import {getAuthHeaders} from '../auth/authHeaders';
import {transformToCamelCase} from '../../utils/apiTransform';

export type CalibrationCaptureReference = {
  id: string;
  stage: 'unified' | 'gaze' | 'camera' | 'guided';
  createdAt: string;
  durationMs: number;
  mediaUrl: string | null;
  usedFor: string[];
  metadata: Record<string, unknown>;
  result: Record<string, unknown> | null;
};
export type CalibrationReference = {
  calibration: Record<string, unknown> | null;
  captures: CalibrationCaptureReference[];
};

export const getCalibrationReference = async (interviewId: number, signal: AbortSignal): Promise<CalibrationReference> => {
  const response = await apiFetch(`${API_URL}/medical-interviews/${interviewId}/calibration/captures`, {headers: getAuthHeaders(), signal});
  if (!response.ok) throw new Error('Calibration reference request failed');
  return transformToCamelCase(await response.json()) as CalibrationReference;
};
