import { API_URL } from '../../utils/request';
import { getAuthHeaders } from '../auth/authHeaders';
import { transformToCamelCase } from '../../utils/apiTransform';
import { InterviewEvaluationResponse } from '../../types/evaluation';

export type InterviewCompletionReason = 'user_completed';

export const completeInterview = async (
  interviewId: string,
  completionReason: InterviewCompletionReason = 'user_completed',
): Promise<InterviewEvaluationResponse> => {
  const authHeaders = getAuthHeaders();
  const response = await fetch(`${API_URL}/medical-interviews/${interviewId}/complete`, {
    method: 'POST',
    body: JSON.stringify({completion_reason: completionReason}),
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
