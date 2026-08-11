import {API_URL} from '../../utils/request';

export type SignInPayload = {
  username: string;
  password: string;
};

export const signIn = async (payload: SignInPayload) => {
  const response = await fetch(`${API_URL}/auth/token`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      accept: 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to sign in');
  }

  return response.json();
};
