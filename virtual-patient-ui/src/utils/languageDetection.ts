/**
 * Detects the browser's default language and returns the appropriate language code
 * @returns 'en' or 'es' based on browser language
 */
export const detectBrowserLanguage = (): string => {
  const browserLang = navigator.language || (navigator as any).userLanguage;
  
  // Check if the browser language starts with 'es' (Spanish)
  if (browserLang.startsWith('es')) {
    return 'es';
  }
  
  // Default to English for all other languages
  return 'en';
};

/**
 * Gets the language code for authentication pages (login/signup)
 * Uses browser detection instead of stored language preference
 * @returns Language code for auth pages
 */
export const getAuthLanguage = (): string => {
  return detectBrowserLanguage();
};
