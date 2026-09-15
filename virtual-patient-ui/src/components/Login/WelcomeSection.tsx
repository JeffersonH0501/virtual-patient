import loginImage from '../../assets/login.svg';
import logoDisc from '../../assets/logo_disc.png';
import {useTranslation} from 'react-i18next';

export const WelcomeSection = () => {
  const {t} = useTranslation();
  return (
    <aside className="auth-welcome">
      <img className="auth-logo" src={logoDisc} alt={t('footer.department')} />
      <div className="auth-welcome-main">
        <div className="auth-welcome-intro">
          <p className="auth-eyebrow">{t('auth.practiceLabel')}</p>
          <h1>{t('auth.appTitle')}</h1>
          <p className="auth-description">{t('auth.appDescription')}</p>
          <img className="auth-illustration" src={loginImage} alt="" />
        </div>
      </div>
      <p className="auth-copyright">{t('footer.copyright')}</p>
    </aside>
  );
};
