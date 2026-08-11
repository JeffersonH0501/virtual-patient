import {API_URL} from '../../utils/request';
import {getAuthHeaders} from '../auth/authHeaders';
import {User} from '../../types';
import {transformToCamelCase, transformToSnakeCase} from '../../utils/apiTransform';

export type UpdateUserPayload = Partial<Pick<User, 'username' | 'email' | 'fullName' | 'preferredLanguage' | 'role'>>;

export const updateUser = async (payload: UpdateUserPayload): Promise<User> => {
  const authHeaders = getAuthHeaders();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    accept: 'application/json',
    ...authHeaders,
  };

  // Convert camelCase to snake_case for API
  const apiPayload = transformToSnakeCase(payload);

  const response = await fetch(`${API_URL}/users/me`, {
    method: 'POST',
    headers,
    body: JSON.stringify(apiPayload),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to update user');
  }

  const data = await response.json();
  return transformToCamelCase(data) as User;
};
