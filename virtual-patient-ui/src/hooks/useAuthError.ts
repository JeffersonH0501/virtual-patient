import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Cookies from 'js-cookie';
import { ROUTES } from '../utils/routes';

export const useAuthError = () => {
  const [isTokenExpired, setIsTokenExpired] = useState(false);
  const navigate = useNavigate();

  const handleTokenExpired = () => {
    // Clear the token
    Cookies.remove('access_token');
    
    // Set token expired state
    setIsTokenExpired(true);
    
    // Redirect to login after showing the error
    setTimeout(() => {
      navigate(ROUTES.signIn);
      setIsTokenExpired(false);
    }, 2000);
  };

  const checkAuthError = (response: Response) => {
    if (response.status === 401) {
      handleTokenExpired();
      return true;
    }
    return false;
  };

  return {
    isTokenExpired,
    checkAuthError,
    handleTokenExpired
  };
};
