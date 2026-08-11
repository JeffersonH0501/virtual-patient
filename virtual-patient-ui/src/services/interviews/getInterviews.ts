import {transformToCamelCase} from '../../utils/apiTransform';
import {API_URL} from '../../utils/request';
import {apiFetch} from '../../utils/apiFetch';
import {getAuthHeaders} from '../auth/authHeaders';
import {InterviewListItem} from '../../types/interview';

export const getInterviews = async (limit = 100, skip = 0) => {
  const authHeaders = getAuthHeaders();
  const params = new URLSearchParams({
    limit: limit.toString(),
    skip: skip.toString(),
  });
  const response = await apiFetch(`${API_URL}/medical-interviews?${params.toString()}`, {
    method: 'GET',
    headers: {
      accept: 'application/json',
      ...authHeaders,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to fetch interviews');
  }

  const data = await response.json();
  return transformToCamelCase(data) as InterviewListItem[];
};
