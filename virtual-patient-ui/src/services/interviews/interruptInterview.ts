import {API_URL} from '../../utils/request';
import {getAuthHeaders} from '../auth/authHeaders';

/**
 * Mark an interview as interrupted. Used when the session did not finish its
 * flow, for example when the student forces its termination on re-entry. No
 * evaluation is generated for an interrupted interview.
 */
export const interruptInterview = async (interviewId: string): Promise<void> => {
  const authHeaders = getAuthHeaders();
  const response = await fetch(`${API_URL}/medical-interviews/${interviewId}/abandon`, {
    method: 'POST',
    headers: {
      accept: 'application/json',
      ...authHeaders,
    },
  });

  if (!response.ok) {
    throw new Error(`HTTP error! status: ${response.status}`);
  }
};
