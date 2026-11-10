import {getAuthHeaders} from '../auth/authHeaders';
import {blockFetch} from '../recordings/blocks';

/**
 * Mark an interview as interrupted. Used when the session did not finish its
 * flow, for example when the student forces its termination on re-entry. No
 * evaluation is generated for an interrupted interview.
 */
export const interruptInterview = async (
  interviewId: string,
  capture?: {segmentId?: string | null; resumeAttemptId?: string; signal?: AbortSignal},
): Promise<void> => {
  const authHeaders = getAuthHeaders();
  const init: RequestInit = {
    signal: capture?.signal,
    method: 'POST',
    headers: {
      accept: 'application/json',
      ...authHeaders,
      ...(capture?.segmentId ? {'X-Capture-Segment': capture.segmentId} : {}),
      ...(capture?.resumeAttemptId ? {'X-Resume-Attempt': capture.resumeAttemptId} : {}),
    },
  };
  const response = await blockFetch(Number(interviewId), '/abandon', init);

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
};
