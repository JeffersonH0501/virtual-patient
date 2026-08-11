import {API_URL} from '../../utils/request';
import {apiFetch} from '../../utils/apiFetch';
import {getAuthHeaders} from '../auth/authHeaders';
import {transformToCamelCase} from '../../utils/apiTransform';
import {User} from '../../types/user';

export const getUser = async (): Promise<User> => {
  const authHeaders = getAuthHeaders();
  const headers: Record<string, string> = {
    accept: 'application/json',
    ...authHeaders,
  };

  const response = await apiFetch(`${API_URL}/users/me`, {
    method: 'GET',
    headers,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to fetch user');
  }

  const data = await response.json();
  return transformToCamelCase(data) as User;
};
