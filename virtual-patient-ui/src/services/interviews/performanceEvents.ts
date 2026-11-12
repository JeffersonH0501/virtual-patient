import {apiFetch} from '../../utils/apiFetch';
import {API_URL} from '../../utils/request';
import {getAuthHeaders} from '../auth/authHeaders';
import {transformToCamelCase} from '../../utils/apiTransform';

export type PerformanceMetadataValue = string | number | boolean | null | PerformanceMetadataValue[] | {[key: string]: PerformanceMetadataValue};

export type InterviewPerformanceEvent = {
  id: number;
  createdAt: string;
  component: string;
  operation: string;
  phase: string;
  status: string;
  durationMs: number | null;
  traceId: string | null;
  metadata: Record<string, PerformanceMetadataValue>;
};

export const getInterviewPerformanceEvents = async (interviewId: number, signal: AbortSignal): Promise<InterviewPerformanceEvent[]> => {
  const response = await apiFetch(`${API_URL}/medical-interviews/${interviewId}/performance-events`, {headers: getAuthHeaders(), signal});
  if (!response.ok) throw new Error('Interview performance request failed');
  return transformToCamelCase(await response.json()) as InterviewPerformanceEvent[];
};
