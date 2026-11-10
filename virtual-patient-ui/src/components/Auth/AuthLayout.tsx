import {useEffect, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {WelcomeSection} from '../Login/WelcomeSection';
import {AuthForm} from './AuthForm';

export const AuthLayout = () => {
  const {i18n} = useTranslation();
  const [mode, setMode] = useState<'signin' | 'signup'>('signin');

  useEffect(() => {
    if (i18n.language !== 'es') void i18n.changeLanguage('es');
  }, [i18n]);

  return (
    <div className="auth-page">
      <main className="auth-card">
        <WelcomeSection />
        <section className="auth-content">
          <AuthForm mode={mode} onSwitchMode={() => setMode(mode === 'signin' ? 'signup' : 'signin')} />
        </section>
      </main>
    </div>
  );
};
