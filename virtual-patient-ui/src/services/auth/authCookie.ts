export const getAuthCookieOptions = () => ({
  sameSite: 'strict' as const,
  secure: window.location.protocol === 'https:',
});
