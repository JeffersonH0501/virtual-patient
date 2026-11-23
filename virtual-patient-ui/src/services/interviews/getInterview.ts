import {transformToCamelCase} from '../../utils/apiTransform';
import {API_URL} from '../../utils/request';
import {apiFetch} from '../../utils/apiFetch';
import {getAuthHeaders} from '../auth/authHeaders';
import {CompleteInterviewResponse} from '../../types/interview';

export const getInterview = async (
  interviewId: string,
  language: 'en' | 'es' = 'en',
  signal?: AbortSignal,
): Promise<CompleteInterviewResponse> => {
  const authHeaders = getAuthHeaders();
  const query = new URLSearchParams({language});
  const response = await apiFetch(`${API_URL}/medical-interviews/${interviewId}/complete?${query}`, {
    method: 'GET',
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(30_000)]) : AbortSignal.timeout(30_000),
    headers: {
      'Content-Type': 'application/json',
      accept: 'application/json',
      ...authHeaders,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw Object.assign(new Error(errorData.detail || 'Failed to fetch interview'), {status: response.status});
  }

  const data = await response.json();
  return transformToCamelCase(data) as CompleteInterviewResponse;
};
