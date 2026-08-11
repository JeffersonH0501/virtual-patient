import Cookies from 'js-cookie';

export const getAuthHeaders = (): Record<string, string> => {
  const token = Cookies.get('access_token');
  return token ? {Authorization: `Bearer ${token}`} : {};
};
