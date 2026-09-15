const API_HOST = import.meta.env.VITE_API_HOST;
const API_PORT = import.meta.env.VITE_API_PORT;

const resolveApiHost = (): string | undefined => {
  if (!API_HOST) return API_HOST;
  try {
    const configured = new URL(API_HOST);
    const loopbackHosts = new Set(['localhost', '127.0.0.1', '0.0.0.0', '']);
    if (
      loopbackHosts.has(configured.hostname)
      || loopbackHosts.has(window.location.hostname)
    ) {
      if (window.location.hostname) {
        configured.hostname = window.location.hostname;
      }
      return configured.toString().replace(/\/$/, '');
    }
  } catch {
    return API_HOST;
  }
  return API_HOST;
};

const RESOLVED_API_HOST = resolveApiHost();

// If API_HOST is empty, undefined, or null, use relative path (Nginx proxy)
// Otherwise, construct full URL with protocol
export const API_URL =
  !RESOLVED_API_HOST || RESOLVED_API_HOST === '' || RESOLVED_API_HOST === 'undefined' || RESOLVED_API_HOST === 'null'
    ? '/api' // Use Nginx proxy
    : API_PORT && API_PORT !== '' && API_PORT !== 'undefined' && API_PORT !== 'null'
      ? `${RESOLVED_API_HOST}:${API_PORT}` // With port
      : RESOLVED_API_HOST; // Without port
