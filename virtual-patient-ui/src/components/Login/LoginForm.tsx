import {FC, FormEvent, useState, useRef, useEffect} from 'react';
import {FormInput, Button} from '../common';
import {useNavigate} from 'react-router-dom';
import {ROUTES} from '../../utils/routes';
import ReCAPTCHA from 'react-google-recaptcha';
import {signIn} from '../../services/auth/signIn';
import Cookies from 'js-cookie';
import {getUser} from '../../services/users/getUser';
import {useTranslation} from 'react-i18next';
import {useUser} from '../../hooks';
import {getAuthCookieOptions} from '../../services/auth/authCookie';

export const LoginForm: FC = () => {
  const [userName, setUserName] = useState('');
  const [password, setPassword] = useState('');
  const [captchaValue, setCaptchaValue] = useState<string | null>(null);
  const [isFormValid, setIsFormValid] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const recaptchaRef = useRef<ReCAPTCHA>(null);
  const navigate = useNavigate();
  const {t} = useTranslation();
  const {setUser} = useUser();

  useEffect(() => {
    // Validate form when inputs change
    const isValid = userName.trim() !== '' && password.trim() !== '' && captchaValue !== null;
    setIsFormValid(isValid);
    // Clear error message when user types
    if (errorMessage) {
      setErrorMessage(null);
    }
  }, [userName, password, captchaValue]);

  const recaptchaSiteKey = import.meta.env.VITE_RECAPTCHA_SITE_KEY;

  if (!recaptchaSiteKey) {
    console.error('Missing reCAPTCHA site key in environment variables');
  }

  const handleCaptchaChange = (value: string | null) => {
    setCaptchaValue(value);
  };

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();

    if (!captchaValue) {
      setErrorMessage(t('errors.captchaVerification'));
      return;
    }

    try {
      const result = await signIn({
        username: userName,
        password,
      });

      if (!result.access_token) {
        setErrorMessage(t('errors.noAccessToken'));
      } else {
        Cookies.set('access_token', result.access_token, getAuthCookieOptions());
        const user = await getUser();
        await setUser(user);
        navigate(ROUTES.clinicalCases);
      }
    } catch (error: any) {
      console.error('Error during login process:', error);
      setErrorMessage(error.message || t('errors.generic'));
      // Reset the CAPTCHA if there's an error
      if (recaptchaRef.current) {
        recaptchaRef.current.reset();
      }
    }
  };

  return (
    <div id="LoginForm" className="flex flex-col ml-5 w-[59%] max-md:ml-0 max-md:w-full">
      <div className="flex flex-col grow px-14 pt-20 pb-24 w-full bg-white max-md:px-5 max-md:pb-24 max-md:mt-10 max-md:max-w-full rounded-r-3xl">
        <h2 className="self-start text-4xl font-bold text-black">{t('auth.welcome')}</h2>
        <p className="self-start mt-3 text-lg font-bold text-black max-md:ml-1.5">
          {t('auth.loginMessage')}
        </p>
        <form
          onSubmit={handleSubmit}
          className="flex flex-col mt-12 w-full text-base font-bold text-black whitespace-nowrap max-md:mt-10 max-md:max-w-full"
        >
          <FormInput
            label={t('auth.userName')}
            type="text"
            id="userName"
            placeholder="johnnydoe"
            value={userName}
            onChange={(e) => setUserName(e.target.value)}
            autoFocus
          />
          <FormInput
            label={t('auth.password')}
            type="password"
            id="password"
            placeholder="********************"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {/* Error message display */}
          {errorMessage && (
            <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
              <p className="text-sm text-red-600 font-medium">{errorMessage}</p>
            </div>
          )}
          {/* reCAPTCHA component */}
          <div className="mt-6 mb-4 max-md:max-w-full flex justify-center">
            <ReCAPTCHA
              ref={recaptchaRef}
              sitekey={recaptchaSiteKey || ''}
              onChange={handleCaptchaChange}
              size="normal"
              theme="light"
            />
          </div>
          <div className="flex flex-col mt-3 max-md:max-w-full">
            <a href="#" className="text-base font-semibold text-blue-600">
              {t('auth.forgotPassword')}
            </a>
            <div className="flex flex-col justify-center items-center mt-4 w-full max-md:max-w-full">
              <Button
                type="submit"
                variant="primary"
                size="lg"
                disabled={!isFormValid}
                className="gap-2 self-stretch px-10 py-3.5 max-w-full text-lg font-bold rounded-xl min-h-[48px] w-[436px] max-md:px-5 w-full"
              >
                {t('auth.login')}
              </Button>
              <p className="mt-2 text-base text-black">
                {t('auth.noAccount')}{' '}
                <a href={ROUTES.signUp} className="text-base font-semibold text-blue-600">
                  {t('auth.signup')}
                </a>
              </p>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};
