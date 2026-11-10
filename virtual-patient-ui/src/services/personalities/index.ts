import {API_URL} from '../../utils/request';
import {getAuthHeaders} from '../auth/authHeaders';
import {Personality} from '../../types';

export const getPersonalities = async (skip = 0, limit = 100): Promise<Personality[]> => {
  const authHeaders = getAuthHeaders();
  const response = await fetch(`${API_URL}/personalities?skip=${skip}&limit=${limit}`, {
    method: 'GET',
    headers: {
      accept: 'application/json',
      ...authHeaders,
    },
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to fetch personalities');
  }

  return response.json();
};
