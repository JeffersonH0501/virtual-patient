/**
 * Language storage utilities for managing language preference in localStorage
 */

const LANGUAGE_STORAGE_KEY = 'virtual-patient-language';

/**
 * Get the stored language preference from localStorage
 * Returns 'en' as default if no preference is stored
 */
export const getStoredLanguage = (): string => {
  try {
    const stored = localStorage.getItem(LANGUAGE_STORAGE_KEY);
    return stored || 'en';
  } catch (error) {
    console.warn('Failed to read language from localStorage:', error);
    return 'en';
  }
};

/**
 * Save language preference to localStorage
 */
export const setStoredLanguage = (language: string): void => {
  try {
    localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
  } catch (error) {
    console.warn('Failed to save language to localStorage:', error);
  }
};

/**
 * Clear the stored language preference
 */
export const clearStoredLanguage = (): void => {
  try {
    localStorage.removeItem(LANGUAGE_STORAGE_KEY);
  } catch (error) {
    console.warn('Failed to clear language from localStorage:', error);
  }
};
