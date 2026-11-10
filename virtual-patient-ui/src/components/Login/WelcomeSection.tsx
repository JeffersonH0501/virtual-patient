import loginImage from '../../assets/login.svg';
import logoDisc from '../../assets/logo_disc.png';
import {useCallback, useState} from 'react';
import {useTranslation} from 'react-i18next';

export const WelcomeSection = () => {
  const {t} = useTranslation();
  const [illustration, setIllustration] = useState<'loading' | 'loaded' | 'unavailable'>('loading');
  const checkCachedIllustration = useCallback((image: HTMLImageElement | null) => {
    if (image?.complete) setIllustration(image.naturalWidth ? 'loaded' : 'unavailable');
  }, []);

  return (
    <aside className="auth-welcome">
      <img className="auth-logo" src={logoDisc} alt={t('footer.department')} />
      <div className="auth-welcome-intro">
        <h1>{t('auth.appTitle')}</h1>
        <p className="auth-description">{t('auth.appDescription')}</p>
      </div>
      <div className="auth-illustration" data-status={illustration} aria-hidden="true">
        <img
          ref={checkCachedIllustration}
          src={loginImage}
          width={524}
          height={376}
          alt=""
          onLoad={() => setIllustration('loaded')}
          onError={() => setIllustration('unavailable')}
        />
      </div>
      <p className="auth-copyright">{t('footer.copyright')}</p>
    </aside>
  );
};
