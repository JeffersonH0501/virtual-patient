import React, {createContext, useCallback, useState, useEffect, ReactNode} from 'react';
import {User} from '../types';
import {getUser, updateUser as updateUserService} from '../services/users';
import i18n from '../i18n';
import {setStoredLanguage, clearStoredLanguage} from '../utils/languageStorage';
import {ROUTES} from '../utils/routes';
import Cookies from 'js-cookie';

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

  const setUser = useCallback(async (userData: User | null) => {
    const language = userData?.preferredLanguage ?? 'es';
    await i18n.changeLanguage(language);
    if (userData) setStoredLanguage(language);
    else clearStoredLanguage();
    setUserState(userData);
  }, []);

  useEffect(() => {
    const loadUser = async () => {
      const path = window.location.pathname;
      const isAuthPage = path === ROUTES.welcome || path === ROUTES.welcome + '/';
      try {
        const userData = !isAuthPage && Cookies.get('access_token') ? await getUser() : null;
        await setUser(userData);
      } catch {
        await setUser(null);
      } finally {
        setIsLoading(false);
      }
    };
    void loadUser();
  }, [setUser]);
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
        await i18n.changeLanguage(language);

        // Reload the page to refetch all data with new language
        window.location.reload();
      } catch (error) {
        console.error('Failed to update user language:', error);
        // Still update the app language locally even if server update fails
        await i18n.changeLanguage(language);

        // Reload the page to refetch all data with new language
        window.location.reload();
      }
    } else {
      // If no user is logged in, just update the app language
      await i18n.changeLanguage(language);
    }
  };

  const signOut = () => {
    // Clear user data
    setUserState(null);

    // Clear language preference from localStorage
    clearStoredLanguage();

    // Reset language to the public default
    void i18n.changeLanguage('es');
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
