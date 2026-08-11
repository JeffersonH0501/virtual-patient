import { API_URL } from '../../utils/request';
import { getAuthHeaders } from '../auth/authHeaders';
import { transformToCamelCase } from '../../utils/apiTransform';
import { InterviewEvaluationResponse } from '../../types/evaluation';

export const completeInterview = async (interviewId: string): Promise<InterviewEvaluationResponse> => {
  const authHeaders = getAuthHeaders();
  const response = await fetch(`${API_URL}/medical-interviews/${interviewId}/complete`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      accept: 'application/json',
      ...authHeaders,
    },
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const data = await response.json();
  return transformToCamelCase(data) as InterviewEvaluationResponse;
};
