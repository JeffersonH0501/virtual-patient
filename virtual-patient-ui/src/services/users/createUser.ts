import {API_URL} from '../../utils/request';

export type CreateUserPayload = {
  email: string;
  // The registration form collects a single "Name" value.
  name: string;
  role: 'student' | 'teacher';
  password: string;
  captcha: string;
};

export type CreateUserResponse = {
  access_token: string;
  token_type: string;
  expires_in?: number;
};

export const createUser = async (payload: CreateUserPayload): Promise<CreateUserResponse> => {
  const {captcha, ...credentials} = payload;
  const response = await fetch(`${API_URL}/users`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      accept: 'application/json',
      'X-Recaptcha-Token': captcha,
    },
    body: JSON.stringify(credentials),
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    if (response.status === 409 || errorData.detail === 'Email already registered') {
      throw new Error('users.errors.duplicate');
    }
    if (response.status === 400) throw new Error('errors.captchaVerification');
    if (response.status === 422) throw new Error('users.errors.invalid');
    throw new Error('auth.signUpFailed');
  }

  return response.json();
};
