import Cookies from 'js-cookie';
import {ROUTES} from './routes';
import {sessionResponse} from './sessionResponses';

// Flag to prevent multiple simultaneous redirects during the same execution
let isRedirecting = false;

// Stable per-tab trace id so backend performance_event lines can be correlated
// with the browser session that triggered them. Opaque; carries no user data.
const traceId: string =
  (globalThis.crypto?.randomUUID?.() ?? Math.random().toString(36).slice(2)).replace(/-/g, '').slice(0, 16);

/**
 * Clear the session and redirect to login on an expired/invalid token.
 * Shared so non-apiFetch paths (e.g. interview capture) recover identically
 * instead of dead-ending the user. Throws a 401-tagged error.
 */
export const handleUnauthorized = (): never => {
  Cookies.remove('access_token');
  const currentPath = window.location.pathname;
  const isOnAuthPage = currentPath === ROUTES.welcome || currentPath === ROUTES.welcome + '/';
  if (!isOnAuthPage && !isRedirecting) {
    isRedirecting = true;
    window.location.href = ROUTES.welcome;
  }
  const error = new Error('Unauthorized') as Error & {status?: number};
  error.status = 401;
  throw error;
};

/**
 * Centralized API fetch wrapper that handles 401 errors globally.
 * When a 401 Unauthorized error occurs, it clears the token and redirects to login.
 *
 * @param url - The API endpoint URL
 * @param options - Fetch options (headers, method, body, etc.)
 * @returns Promise<Response>
 */
export const apiFetch = async (
  url: string,
  options: RequestInit = {},
): Promise<Response> => {
  // Attach the trace id to every request without touching individual callers.
  options = {...options, headers: {...(options.headers as Record<string, string> | undefined), 'X-Trace-Id': traceId}};
  const response = await sessionResponse(url, options, (shared) => fetch(url, shared ? {...options, signal: undefined} : options));

  // Handle 401 Unauthorized globally
  if (response.status === 401) handleUnauthorized();

  // Reset redirect flag on successful requests
  isRedirecting = false;

  return response;
};
