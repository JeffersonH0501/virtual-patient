import {transformToCamelCase} from '../../utils/apiTransform';
import {API_URL} from '../../utils/request';
import {apiFetch} from '../../utils/apiFetch';
import {getAuthHeaders} from '../auth/authHeaders';
import {Status} from '../../types/interview';

export type ActiveInterview = {
  id: number;
  publicId: string;
  status: Status;
  startTime: string | null;
};

/**
 * Return the current user's in-progress interview, if any. The backend only
 * reports an interview that has started and has not been completed or
 * interrupted, so the client can offer to resume it or force its termination
 * when the student re-enters the application.
 */
export const getActiveInterview = async (): Promise<ActiveInterview | null> => {
  const authHeaders = getAuthHeaders();
  const response = await apiFetch(`${API_URL}/medical-interviews/my/active`, {
    method: 'GET',
    headers: {
      accept: 'application/json',
      ...authHeaders,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to fetch active interview');
  }

  const data = await response.json();
  if (!data) return null;
  return transformToCamelCase(data) as ActiveInterview;
};
