import React, {createContext, useState, useEffect, ReactNode} from 'react';
import {User} from '../types';
import {getUser, updateUser as updateUserService} from '../services/users';
import i18n from '../i18n';
import {getStoredLanguage, setStoredLanguage, clearStoredLanguage} from '../utils/languageStorage';
import {ROUTES} from '../utils/routes';

// The API returns language codes directly (en, es) which match i18n codes

interface UserContextType {
  user: User | null;
  setUser: (user: User | null) => Promise<void>;
  updateUser: (updates: Partial<User>) => void;
  updateUserLanguage: (language: string) => Promise<void>;
  signOut: () => void;
  isLoading: boolean;
}

export const UserContext = createContext<UserContextType | undefined>(undefined);

interface UserProviderProps {
  children: ReactNode;
}

export const UserProvider: React.FC<UserProviderProps> = ({children}) => {
  const [user, setUserState] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Custom setUser that handles language preferences
  const setUser = async (userData: User | null) => {
    setUserState(userData);
    
    if (userData?.preferredLanguage) {
      console.log('Setting language to user preference:', userData.preferredLanguage);
      
      // Wait for i18n to be ready if it's not already
      if (!i18n.isInitialized) {
        console.log('Waiting for i18n to initialize...');
        await new Promise((resolve) => {
          i18n.on('initialized', resolve);
        });
      }
      
      await i18n.changeLanguage(userData.preferredLanguage);
      setStoredLanguage(userData.preferredLanguage);
      console.log('Current i18n language after change:', i18n.language);
    }
  };

  // Load user on mount if authenticated (but not on login/signup pages)
  useEffect(() => {
    const loadUser = async () => {
      // Check if we're on an auth page (login or signup)
      const currentPath = window.location.pathname;
      const isOnAuthPage = currentPath === ROUTES.home || currentPath === ROUTES.signUp;
      
      // Don't try to fetch user on auth pages
      if (isOnAuthPage) {
        setUserState(null);
        
        // Initialize with stored language or default to English
        const storedLanguage = getStoredLanguage();

        // Wait for i18n to be ready if it's not already
        if (!i18n.isInitialized) {
          console.log('Waiting for i18n to initialize...');
          await new Promise((resolve) => {
            i18n.on('initialized', resolve);
          });
        }

        await i18n.changeLanguage(storedLanguage);
        setIsLoading(false);
        return;
      }

      // Try to fetch user if not on auth page
      try {
        const userData = await getUser();
        setUserState(userData);
        console.log('User data:', userData);

        // Wait for i18n to be ready if it's not already
        if (!i18n.isInitialized) {
          console.log('Waiting for i18n to initialize...');
          await new Promise((resolve) => {
            i18n.on('initialized', resolve);
          });
        }

        // If user has a preferred language, use it and save to localStorage
        if (userData.preferredLanguage) {
          console.log('Setting language to user preference:', userData.preferredLanguage);
          await i18n.changeLanguage(userData.preferredLanguage);
          setStoredLanguage(userData.preferredLanguage);
          console.log('Current i18n language after change:', i18n.language);
        } else {
          // If user has no preferred language, use stored language or default to English
          const storedLanguage = getStoredLanguage();
          console.log('User has no preferred language, using stored:', storedLanguage);
          await i18n.changeLanguage(storedLanguage);
        }
      } catch (error) {
        // User not authenticated or error loading user
        setUserState(null);

        // If no user is logged in, initialize with stored language or default to English
        const storedLanguage = getStoredLanguage();
        console.log('No user logged in, using stored language:', storedLanguage);

        // Wait for i18n to be ready if it's not already
        if (!i18n.isInitialized) {
          console.log('Waiting for i18n to initialize...');
          await new Promise((resolve) => {
            i18n.on('initialized', resolve);
          });
        }

        await i18n.changeLanguage(storedLanguage);
      } finally {
        setIsLoading(false);
      }
    };

    loadUser();
  }, []);

  const updateUser = (updates: Partial<User>) => {
    if (user) {
      setUserState({...user, ...updates});
    }
  };

  const updateUserLanguage = async (language: string) => {
    // Always save to localStorage first
    setStoredLanguage(language);

    if (user) {
      try {
        // Update user's preferred language on the server
        const updatedUser = await updateUserService({preferredLanguage: language});
        setUserState(updatedUser);
        // Update app language
        console.log('Updating language to:', language);
        await i18n.changeLanguage(language);
        console.log('Current i18n language after update:', i18n.language);
        
        // Reload the page to refetch all data with new language
        window.location.reload();
      } catch (error) {
        console.error('Failed to update user language:', error);
        // Still update the app language locally even if server update fails
        console.log('Updating language locally after error:', language);
        await i18n.changeLanguage(language);
        
        // Reload the page to refetch all data with new language
        window.location.reload();
      }
    } else {
      // If no user is logged in, just update the app language
      console.log('Updating language for non-logged user:', language);
      await i18n.changeLanguage(language);
    }
  };

  const signOut = () => {
    // Clear user data
    setUserState(null);

    // Clear language preference from localStorage
    clearStoredLanguage();

    // Reset language to default (English)
    i18n.changeLanguage('en');

    console.log('User signed out, language storage cleared');
  };

  const value: UserContextType = {
    user,
    setUser,
    updateUser,
    updateUserLanguage,
    signOut,
    isLoading,
  };

  return <UserContext.Provider value={value}>{children}</UserContext.Provider>;
};
