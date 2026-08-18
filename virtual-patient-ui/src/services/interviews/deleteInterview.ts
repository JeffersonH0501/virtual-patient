import {apiFetch} from '../../utils/apiFetch';
import {API_URL} from '../../utils/request';
import {getAuthHeaders} from '../auth/authHeaders';

export const deleteInterview = async (interviewId: number): Promise<void> => {
  const response = await apiFetch(`${API_URL}/medical-interviews/${interviewId}`, {
    method: 'DELETE',
    headers: {
      accept: 'application/json',
      ...getAuthHeaders(),
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to delete interview');
  }
};
