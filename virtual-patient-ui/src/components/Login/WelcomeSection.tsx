import loginImage from '../../assets/login.svg';
import logoDisc from '../../assets/logo_disc.png';
import {useTranslation} from 'react-i18next';

export const WelcomeSection = () => {
  const {t} = useTranslation();
  return (
    <aside className="auth-welcome">
      <img className="auth-logo" src={logoDisc} alt={t('footer.department')} />
      <div>
        <p className="auth-eyebrow">{t('auth.practiceLabel')}</p>
        <h1>{t('auth.appTitle')}</h1>
        <p className="auth-description">{t('auth.appDescription')}</p>
      </div>
      <img className="auth-illustration" src={loginImage} alt="" />
      <p className="auth-institution">{t('footer.university')}</p>
    </aside>
  );
};
