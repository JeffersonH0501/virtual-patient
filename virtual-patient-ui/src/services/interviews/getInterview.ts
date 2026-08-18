import {transformToCamelCase} from '../../utils/apiTransform';
import {API_URL} from '../../utils/request';
import {apiFetch} from '../../utils/apiFetch';
import {getAuthHeaders} from '../auth/authHeaders';
import {CompleteInterviewResponse} from '../../types/interview';

export const getInterview = async (
  interviewId: string,
  language: 'en' | 'es' = 'en',
): Promise<CompleteInterviewResponse> => {
  const authHeaders = getAuthHeaders();
  const query = new URLSearchParams({language});
  const response = await apiFetch(`${API_URL}/medical-interviews/${interviewId}/complete?${query}`, {
    method: 'GET',
    headers: {
      'Content-Type': 'application/json',
      accept: 'application/json',
      ...authHeaders,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to fetch interview');
  }

  const data = await response.json();
  return transformToCamelCase(data) as CompleteInterviewResponse;
};
