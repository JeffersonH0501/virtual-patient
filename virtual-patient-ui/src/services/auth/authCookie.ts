export const getAuthCookieOptions = (expiresInSeconds = 480 * 60) => ({
  sameSite: 'strict' as const,
  secure: window.location.protocol === 'https:',
  expires: expiresInSeconds / 86400,
});
