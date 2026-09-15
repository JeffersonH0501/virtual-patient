import {API_URL} from '../../utils/request';

export type CreateUserPayload = {
  email: string;
  // The registration form collects a single "Name" value, sent as first_name.
  first_name: string;
  last_name?: string;
  password: string;
  role?: 'student' | 'teacher'; // Make optional until backend supports it
};

export type CreateUserResponse = {
  access_token: string;
  token_type: string;
};

export const createUser = async (payload: CreateUserPayload): Promise<CreateUserResponse> => {
  const response = await fetch(`${API_URL}/users`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      accept: 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to sign up');
  }

  return response.json();
};
