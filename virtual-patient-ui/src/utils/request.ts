const API_HOST = import.meta.env.VITE_API_HOST;
const API_PORT = import.meta.env.VITE_API_PORT;

// If API_HOST is empty, undefined, or null, use relative path (Nginx proxy)
// Otherwise, construct full URL with protocol
export const API_URL =
  !API_HOST || API_HOST === '' || API_HOST === 'undefined' || API_HOST === 'null'
    ? '/api' // Use Nginx proxy
    : API_PORT && API_PORT !== '' && API_PORT !== 'undefined' && API_PORT !== 'null'
      ? `${API_HOST}:${API_PORT}` // With port
      : API_HOST; // Without port

