import Cookies from 'js-cookie';
import {ROUTES} from './routes';

// Flag to prevent multiple simultaneous redirects during the same execution
let isRedirecting = false;

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
  options: RequestInit = {}
): Promise<Response> => {
  const response = await fetch(url, options);

  // Handle 401 Unauthorized globally
  if (response.status === 401) {
    // Clear the access token
    Cookies.remove('access_token');
    
    // Check if we're already on the login or signup page to avoid redirect loops
    const currentPath = window.location.pathname;
    const isOnAuthPage = [ROUTES.signIn, ROUTES.signUp, ROUTES.resetPassword].includes(currentPath);
    
    // Only redirect if we're not already on an auth page
    // This prevents infinite redirect loops when UserContext calls getUser() on the login page
    if (!isOnAuthPage && !isRedirecting) {
      isRedirecting = true;
      // Redirect to login page immediately
      // Using window.location.href to ensure navigation works outside React context
      window.location.href = ROUTES.signIn;
    }
    
    // Throw error with status to allow error handling if needed
    const error = new Error('Unauthorized') as Error & { status?: number };
    error.status = 401;
    throw error;
  }

  // Reset redirect flag on successful requests
  isRedirecting = false;

  return response;
};
