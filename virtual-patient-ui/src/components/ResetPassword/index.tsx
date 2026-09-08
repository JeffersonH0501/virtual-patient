import {Link} from 'react-router-dom';
import {useTranslation} from 'react-i18next';
import {AuthLayout} from '../Auth/AuthLayout';
import {AuthField} from '../Auth/AuthField';
import {ROUTES} from '../../utils/routes';

export const ResetPassword = () => {
  const {t} = useTranslation();
  return (
    <AuthLayout>
      <div className="auth-form-container">
        <header className="auth-form-heading">
          <p className="auth-eyebrow">{t('auth.accountAccess')}</p>
          <h2>{t('auth.resetTitle')}</h2>
          <p>{t('auth.resetDescription')}</p>
        </header>
        <form className="auth-form" onSubmit={(event) => event.preventDefault()}>
          <AuthField id="reset-email" label={t('auth.email')} type="email"
            name="email" autoComplete="email" placeholder={t('auth.emailPlaceholder')} />
          <p className="auth-notice" id="reset-availability">{t('auth.resetUnavailable')}</p>
          <button className="auth-submit" type="submit" disabled aria-describedby="reset-availability">
            {t('auth.resetAction')}
          </button>
          <p className="auth-switch"><Link to={ROUTES.signIn}>{t('auth.backToSignIn')}</Link></p>
        </form>
      </div>
    </AuthLayout>
  );
};
