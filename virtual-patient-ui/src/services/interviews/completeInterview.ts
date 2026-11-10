import { getAuthHeaders } from '../auth/authHeaders';
import { transformToCamelCase } from '../../utils/apiTransform';
import { InterviewEvaluationResponse } from '../../types/evaluation';
import {blockFetch} from '../recordings/blocks';

export type InterviewCompletionReason = 'user_completed';

export const completeInterview = async (
  interviewId: string,
  completionReason: InterviewCompletionReason = 'user_completed',
  captureSegmentId?: string | null,
): Promise<InterviewEvaluationResponse> => {
  const authHeaders = getAuthHeaders();
  const init: RequestInit = {
    method: 'POST',
    body: JSON.stringify({completion_reason: completionReason}),
    headers: {
      'Content-Type': 'application/json',
      accept: 'application/json',
      ...authHeaders,
      ...(captureSegmentId ? {'X-Capture-Segment': captureSegmentId} : {}),
    },
  };
  const response = await blockFetch(Number(interviewId), '/complete', init);

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }

  const data = await response.json();
  return transformToCamelCase(data) as InterviewEvaluationResponse;
};
