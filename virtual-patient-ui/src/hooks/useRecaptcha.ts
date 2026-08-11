import {useEffect, useCallback} from 'react';

declare global {
  interface Window {
    grecaptcha: {
      ready: (callback: () => void) => void;
      execute: (siteKey: string, options: {action: string}) => Promise<string>;
    };
  }
}

export const useRecaptcha = (siteKey: string) => {
  useEffect(() => {
    // Load reCAPTCHA script if not already loaded
    if (!document.querySelector('script[src*="recaptcha"]')) {
      const script = document.createElement('script');
      script.src = `https://www.google.com/recaptcha/enterprise.js?render=${siteKey}`;
      script.async = true;
      script.defer = true;
      document.head.appendChild(script);
    }
  }, [siteKey]);

  const executeRecaptcha = useCallback(
    async (action: string = 'submit'): Promise<string> => {
      return new Promise((resolve, reject) => {
        if (!window.grecaptcha) {
          reject(new Error('reCAPTCHA not loaded'));
          return;
        }

        window.grecaptcha.ready(() => {
          window.grecaptcha
            .execute(siteKey, {action})
            .then((token: string) => {
              resolve(token);
            })
            .catch((error: any) => {
              reject(error);
            });
        });
      });
    },
    [siteKey],
  );

  return {executeRecaptcha};
};
