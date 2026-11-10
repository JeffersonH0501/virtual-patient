import {FormEvent, useRef, useState} from 'react';
import {useNavigate} from 'react-router-dom';
import {useTranslation} from 'react-i18next';
import ReCAPTCHA from 'react-google-recaptcha';
import Cookies from 'js-cookie';
import {AuthField} from './AuthField';
import {Button} from '../common/Button';
import {Select} from '../common/Select';
import {MotionContent, MotionHeight} from '../common/Motion';
import {ROUTES} from '../../utils/routes';
import {signIn} from '../../services/auth/signIn';
import {createUser, type CreateUserPayload} from '../../services/users/createUser';
import {getUser} from '../../services/users/getUser';
import {getAuthCookieOptions} from '../../services/auth/authCookie';
import {useUser} from '../../hooks/useUser';

export const AuthForm = ({mode, onSwitchMode}: {mode: 'signin' | 'signup'; onSwitchMode: () => void}) => {
  const registering = mode === 'signup';
  const {t} = useTranslation();
  const {setUser} = useUser();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [name, setName] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState<CreateUserPayload['role'] | ''>('');
  const [captcha, setCaptcha] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const captchaRef = useRef<ReCAPTCHA>(null);
  const siteKey = import.meta.env.VITE_RECAPTCHA_SITE_KEY;
  const valid = email.trim() && password.trim() && captcha
    && (!registering || (name.trim() && role));

  const switchMode = () => {
    setEmail('');
    setName('');
    setPassword('');
    setRole('');
    setError('');
    onSwitchMode();
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!valid || !captcha || busy || (registering && !role)) return;
    setBusy(true);
    setError('');
    try {
      const result = registering && role
        ? await createUser({email: email.trim(), name: name.trim(), password, role, captcha})
        : await signIn({email: email.trim(), password, captcha});
      if (!result.access_token) throw new Error('errors.noAccessToken');
      Cookies.set('access_token', result.access_token, getAuthCookieOptions(result.expires_in));
      await setUser(await getUser());
      navigate(ROUTES.clinicalCases);
    } catch (failure: unknown) {
      setError(failure instanceof Error ? failure.message : 'errors.generic');
      captchaRef.current?.reset();
      setCaptcha(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-form-container">
      <MotionContent changeKey={mode}>
        <header className="auth-form-heading">
          <h2>{t(registering ? 'auth.createAccount' : 'auth.welcome')}</h2>
          <p>{t(registering ? 'auth.signupMessage' : 'auth.loginMessage')}</p>
        </header>
      </MotionContent>
      <form className="auth-form" onSubmit={submit} aria-busy={busy}>
        <div>
          <MotionHeight expanded={registering} fade={false}>
            {registering && <div className="pb-inset">
              <AuthField label={t('auth.name')} id="name" name="name" autoComplete="name"
                value={name} onChange={(event) => setName(event.target.value)} required />
            </div>}
          </MotionHeight>
          <div className="mb-inset">
            <AuthField label={t('auth.email')} id="email" name="email" type="email" autoComplete="email"
              autoCapitalize="none" spellCheck={false}
              value={email} onChange={(event) => setEmail(event.target.value)} required />
          </div>
          <MotionHeight expanded={registering} fade={false}>
            {registering && <div className="pb-inset">
              <div className="ui-field">
                <label htmlFor="signup-role">{t('auth.role')}</label>
                <Select id="signup-role" label={t('auth.role')} placeholder={t('users.selectRole')}
                  value={role} onValueChange={(value) => {
                    if (value === 'student' || value === 'teacher') setRole(value);
                  }}
                  options={[
                    {value: 'student', label: t('auth.student')},
                    {value: 'teacher', label: t('auth.teacher')},
                  ]} />
              </div>
            </div>}
          </MotionHeight>
          <AuthField label={t('auth.password')} id="password" name="password" type="password"
            autoComplete={registering ? 'new-password' : 'current-password'}
            value={password} onChange={(event) => setPassword(event.target.value)} required />
        </div>
        {error && <p className="auth-error" role="alert">{t(error, {defaultValue: t('errors.generic')})}</p>}
        {siteKey ? (
          <div className="auth-captcha">
            {/* @ts-expect-error: The installed reCAPTCHA types target an older React version. */}
            <ReCAPTCHA ref={captchaRef} sitekey={siteKey} onChange={setCaptcha}
              onExpired={() => setCaptcha(null)}
              onErrored={() => {
                setCaptcha(null);
                setError('errors.captchaVerification');
              }}
              size="normal" theme="light" />
          </div>
        ) : <p className="auth-notice" role="status">{t('auth.verificationUnavailable')}</p>}
        <Button type="submit" disabled={!valid || busy}>
          {t(busy ? (registering ? 'auth.creatingAccount' : 'auth.signingIn') : (registering ? 'auth.signup' : 'auth.login'))}
        </Button>
        <p className="auth-switch">
          {t(registering ? 'auth.alreadyHaveAccount' : 'auth.noAccount')}{' '}
          <button type="button" onClick={switchMode} disabled={busy}>
            {t(registering ? 'auth.signIn' : 'auth.signup')}
          </button>
        </p>
      </form>
    </div>
  );
};
