import { CreateSummaryResponse, ProgressSummary } from '../../types';
import { transformToCamelCase } from '../../utils/apiTransform';
import { API_URL } from '../../utils/request';
import { getAuthHeaders } from '../auth/authHeaders';

export const createSummary = async (
  interviewId: string,
  language: 'en' | 'es' = 'en',
): Promise<CreateSummaryResponse> => {
  const authHeaders = getAuthHeaders();
  const query = new URLSearchParams({language});
  const response = await fetch(`${API_URL}/medical-interviews/${interviewId}/summary?${query}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      accept: 'application/json',
      ...authHeaders,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to create summary');
  }

  const data = await response.json();
  return {
    summary_result: data.summary_result ? transformToCamelCase(data.summary_result) as ProgressSummary : null,
  };
};
