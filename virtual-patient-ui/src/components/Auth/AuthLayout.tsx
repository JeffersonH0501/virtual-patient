import {ReactNode, useEffect} from 'react';
import {useTranslation} from 'react-i18next';
import {getAuthLanguage} from '../../utils/languageDetection';
import {WelcomeSection} from '../Login/WelcomeSection';

export const AuthLayout = ({children}: {children: ReactNode}) => {
  const {t, i18n} = useTranslation();

  useEffect(() => {
    const language = getAuthLanguage();
    if (i18n.language !== language) void i18n.changeLanguage(language);
  }, [i18n]);

  return (
    <div className="auth-page">
      <main className="auth-card">
        <WelcomeSection />
        <section className="auth-content">{children}</section>
      </main>
      <footer className="auth-footer">
        <span>{t('footer.copyright')}</span>
        <a href="https://sistemas.uniandes.edu.co/es/" target="_blank" rel="noopener noreferrer">
          {t('footer.department')}
        </a>
      </footer>
    </div>
  );
};

