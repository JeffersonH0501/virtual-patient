import {API_URL} from '../../utils/request';
import {getAuthHeaders} from '../auth/authHeaders';

export type CreateUserPayload = {
  email: string;
  // The registration form collects a single "Name" value.
  name: string;
  role: 'student' | 'doctor';
  semester_range?: 'first_four' | 'fifth_eighth' | 'ninth_plus';
  university?: string;
  password: string;
  captcha: string;
};

export const createUser = async (payload: CreateUserPayload): Promise<void> => {
  const {captcha, ...credentials} = payload;
  const response = await fetch(`${API_URL}/users`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      ...getAuthHeaders(),
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

};
