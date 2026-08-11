import {transformToCamelCase} from '../../utils/apiTransform';
import {API_URL} from '../../utils/request';
import {apiFetch} from '../../utils/apiFetch';
import {getAuthHeaders} from '../auth/authHeaders';
import {CompleteInterviewResponse} from '../../types/interview';

export const getInterview = async (interviewId: string): Promise<CompleteInterviewResponse> => {
  const authHeaders = getAuthHeaders();
  const response = await apiFetch(`${API_URL}/medical-interviews/${interviewId}`, {
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
  console.log("data", data);
  return transformToCamelCase(data) as CompleteInterviewResponse;
};
