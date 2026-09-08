import {FormEvent, useRef, useState} from 'react';
import {Link, useNavigate} from 'react-router-dom';
import {useTranslation} from 'react-i18next';
import ReCAPTCHA from 'react-google-recaptcha';
import Cookies from 'js-cookie';
import {AuthField} from './AuthField';
import {ROUTES} from '../../utils/routes';
import {signIn} from '../../services/auth/signIn';
import {createUser} from '../../services/users/createUser';
import {getUser} from '../../services/users/getUser';
import {getAuthCookieOptions} from '../../services/auth/authCookie';
import {useUser} from '../../hooks/useUser';

export const AuthForm = ({mode}: {mode: 'signin' | 'signup'}) => {
  const registering = mode === 'signup';
  const {t} = useTranslation();
  const {setUser} = useUser();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<'student' | 'teacher'>('student');
  const [captcha, setCaptcha] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const captchaRef = useRef<ReCAPTCHA>(null);
  const siteKey = import.meta.env.VITE_RECAPTCHA_SITE_KEY;
  const valid = email.trim() && password.trim() && captcha
    && (!registering || (firstName.trim() && lastName.trim()));

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!valid || busy) return;
    setBusy(true);
    setError('');
    try {
      const result = registering
        ? await createUser({email: email.trim(), first_name: firstName.trim(),
          last_name: lastName.trim(), password, role})
        : await signIn({email: email.trim(), password});
      if (!result.access_token) throw new Error(t('errors.noAccessToken'));
      Cookies.set('access_token', result.access_token, getAuthCookieOptions());
      await setUser(await getUser());
      navigate(ROUTES.clinicalCases);
    } catch (failure: unknown) {
      setError(failure instanceof Error ? failure.message : t('errors.generic'));
      captchaRef.current?.reset();
      setCaptcha(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-form-container">
      <header className="auth-form-heading">
        <p className="auth-eyebrow">{t('auth.accountAccess')}</p>
        <h2>{t(registering ? 'auth.createAccount' : 'auth.welcome')}</h2>
        <p>{t(registering ? 'auth.signupMessage' : 'auth.loginMessage')}</p>
      </header>
      <form className="auth-form" onSubmit={submit} aria-busy={busy}>
        <div className={registering ? 'auth-fields-grid' : 'auth-fields-stack'}>
          {registering && (
            <>
              <AuthField label={t('auth.firstName')} id="first-name" name="given-name" autoComplete="given-name"
                value={firstName} onChange={(event) => setFirstName(event.target.value)} required />
              <AuthField label={t('auth.lastName')} id="last-name" name="family-name" autoComplete="family-name"
                value={lastName} onChange={(event) => setLastName(event.target.value)} required />
            </>
          )}
          <div className="auth-field-wide">
            <AuthField label={t('auth.email')} id="email" name="email" type="email" autoComplete="email"
              autoCapitalize="none" spellCheck={false}
              value={email} onChange={(event) => setEmail(event.target.value)} required />
          </div>
          <AuthField label={t('auth.password')} id="password" name="password" type="password"
            autoComplete={registering ? 'new-password' : 'current-password'}
            value={password} onChange={(event) => setPassword(event.target.value)} required />
          {registering && (
            <div className="auth-field">
              <label htmlFor="role">{t('auth.role')}</label>
              <select id="role" value={role} onChange={(event) => setRole(event.target.value as 'student' | 'teacher')}>
                <option value="student">{t('auth.student')}</option>
                <option value="teacher">{t('auth.teacher')}</option>
              </select>
            </div>
          )}
        </div>
        {!registering && <Link className="auth-forgot" to={ROUTES.resetPassword}>{t('auth.forgotPassword')}</Link>}
        {error && <p className="auth-error" role="alert">{error}</p>}
        {siteKey ? (
          <div className="auth-captcha">
            {/* @ts-expect-error: The installed reCAPTCHA types target an older React version. */}
            <ReCAPTCHA ref={captchaRef} sitekey={siteKey} onChange={setCaptcha}
              onExpired={() => setCaptcha(null)}
              onErrored={() => {
                setCaptcha(null);
                setError(t('errors.captchaVerification'));
              }}
              size="normal" theme="light" />
          </div>
        ) : <p className="auth-notice" role="status">{t('auth.verificationUnavailable')}</p>}
        <button className="auth-submit" type="submit" disabled={!valid || busy}>
          {t(busy ? (registering ? 'auth.creatingAccount' : 'auth.signingIn') : (registering ? 'auth.signup' : 'auth.login'))}
        </button>
        <p className="auth-switch">
          {t(registering ? 'auth.alreadyHaveAccount' : 'auth.noAccount')}{' '}
          <Link to={registering ? ROUTES.signIn : ROUTES.signUp}>
            {t(registering ? 'auth.signIn' : 'auth.signup')}
          </Link>
        </p>
      </form>
    </div>
  );
};
