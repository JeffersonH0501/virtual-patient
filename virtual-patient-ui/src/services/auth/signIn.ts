import {API_URL} from '../../utils/request';

export type SignInPayload = {
  email: string;
  password: string;
  captcha: string;
};

export const signIn = async (payload: SignInPayload) => {
  const {captcha, ...credentials} = payload;
  const response = await fetch(`${API_URL}/auth/token`, {
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
    if (response.status === 401) throw new Error('auth.invalidCredentials');
    if (response.status === 400) throw new Error('errors.captchaVerification');
    throw new Error('auth.signInFailed');
  }

  return response.json();
};
