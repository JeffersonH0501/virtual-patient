import {FC, FormEvent, useState, useRef, useEffect} from 'react';
import {FormInput} from '../common';
import ReCAPTCHA from 'react-google-recaptcha';
import {ROUTES} from '../../utils/routes';
import {createUser} from '../../services/users/createUser';
import Cookies from 'js-cookie';
import {getUser} from '../../services/users/getUser';
import {useNavigate} from 'react-router-dom';
import {useUser} from '../../hooks';
import {useTranslation} from 'react-i18next';
import {getAuthCookieOptions} from '../../services/auth/authCookie';

export const SignUpForm: FC = () => {
  const [email, setEmail] = useState('');
  const [username, setUsername] = useState('');
  const [fullName, setFullName] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<'student' | 'teacher'>('student');
  const [captchaValue, setCaptchaValue] = useState<string | null>(null);
  const [isFormValid, setIsFormValid] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const recaptchaRef = useRef<ReCAPTCHA>(null);
  const {setUser} = useUser();
  const navigate = useNavigate();
  const {t} = useTranslation();

  useEffect(() => {
    // Validate form when inputs change
    const isValid =
      email.trim() !== '' &&
      username.trim() !== '' &&
      fullName.trim() !== '' &&
      password.trim() !== '' &&
      captchaValue !== null;
    setIsFormValid(isValid);
  }, [email, username, fullName, password, captchaValue]);

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
      alert(t('errors.captchaVerification'));
      return;
    }

    try {
      setIsLoading(true);

      const result = await createUser({
        username,
        email,
        full_name: fullName,
        password,
        role,
      });

      if (!result.access_token) {
        throw new Error('No access token received');
      }

      // Store the access_token in cookies
      Cookies.set('access_token', result.access_token, getAuthCookieOptions());

      // Fetch user data after successful sign up
      const user = await getUser();

      // Store user in global context
      setUser(user);

      // Reset form
      setEmail('');
      setUsername('');
      setFullName('');
      setPassword('');
      setRole('student');
      setCaptchaValue(null);
      recaptchaRef.current?.reset();

      // Navigate to clinical cases page
      navigate(ROUTES.clinicalCases);
    } catch (error: any) {
      console.error('Sign up error:', error);
      alert(error.message || t('errors.generic'));
      if (recaptchaRef.current) {
        recaptchaRef.current.reset();
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div id="SignUpForm" className="flex flex-col ml-5 w-[59%] max-md:ml-0 max-md:w-full">
      <div className="flex flex-col grow px-14 pt-20 pb-24 w-full bg-white max-md:px-5 max-md:pb-24 max-md:mt-10 max-md:max-w-full rounded-r-3xl">
        <h2 className="self-start text-4xl font-bold text-black">Create Account</h2>
        <p className="self-start mt-3 text-lg font-bold text-black max-md:ml-1.5">
          Please sign up to create your account
        </p>
        <form
          onSubmit={handleSubmit}
          className="flex flex-col mt-12 w-full text-base font-bold text-black whitespace-nowrap max-md:mt-10 max-md:max-w-full"
        >
          <FormInput
            label="Email"
            type="email"
            id="email"
            placeholder="johndoe@gmail.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <FormInput
            label="User Name"
            type="text"
            id="username"
            placeholder="johnnydoe"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
          <FormInput
            label="Full Name"
            type="text"
            id="fullName"
            placeholder="John Doe"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
          />
          <FormInput
            label="Password"
            type="password"
            id="password"
            placeholder="********************"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />

          {/* Role selection */}
          <div className="flex flex-col mt-6 mb-4">
            <label htmlFor="role" className="text-sm font-medium text-gray-900 mb-2">
              Role
            </label>
            <select
              id="role"
              value={role}
              onChange={(e) => setRole(e.target.value as 'student' | 'teacher')}
              className="px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="student">Student</option>
              <option value="teacher">Teacher/Instructor</option>
            </select>
          </div>

          {/* reCAPTCHA component */}
          <div className="mt-6 mb-4 max-md:max-w-full flex justify-center">
            {/* @ts-expect-error: ReCAPTCHA type definitions may be incompatible with usage in this context */}
            <ReCAPTCHA
              ref={recaptchaRef}
              sitekey={recaptchaSiteKey || ''}
              onChange={handleCaptchaChange}
              size="normal"
              theme="light"
            />
          </div>
          <div className="flex flex-col mt-3 max-md:max-w-full">
            <div className="flex flex-col justify-center items-center mt-4 w-full max-md:max-w-full">
              <button
                type="submit"
                className={`gap-2 self-stretch px-10 py-3.5 max-w-full text-lg font-bold text-white rounded-xl min-h-[48px] w-[436px] max-md:px-5 w-full ${
                  isFormValid && !isLoading ? 'bg-blue-600' : 'bg-blue-300 cursor-not-allowed'
                }`}
                disabled={!isFormValid || isLoading}
              >
                {isLoading ? 'Creating Account...' : 'Sign up'}
              </button>
              <p className="mt-2 text-base text-black">
                Already have an account?{' '}
                <a href={ROUTES.home} className="text-base font-semibold text-blue-600">
                  Sign in
                </a>
              </p>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
};
