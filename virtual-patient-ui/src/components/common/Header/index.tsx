import {FC, useEffect, useRef, useState} from 'react';
import {Info, CircleUserRound} from 'lucide-react';
import {Link, useLocation, useNavigate} from 'react-router-dom';
import {getNavigationSection, NavigationSection, ROUTES} from '../../../utils/routes';
import {Menu} from '../Menu';
import {HelpModal} from '../HelpModal';
import logoDisc from '/src/assets/logo_disc.png';
import Cookies from 'js-cookie';
import {useTranslation} from 'react-i18next';
import {useUser} from '../../../hooks';
import {API_URL} from '../../../utils/request';
import {getAuthHeaders} from '../../../services/auth/authHeaders';
import {MotionPresence} from '../Motion';
import {loadSurvey, Survey} from '../../../services/perceptionSurvey';

export const Header: FC = () => {
  const {pathname} = useLocation();
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isHelpModalOpen, setIsHelpModalOpen] = useState(false);
  const profileButtonReference = useRef<HTMLButtonElement>(null);
  const navigate = useNavigate();
  const {t} = useTranslation();
  const {user, signOut} = useUser();
  const [survey, setSurvey] = useState<Survey | null>(null);
  useEffect(() => {
    let active = true;
    setSurvey(null);
    if (!user || user.role === 'superuser') return () => { active = false; };
    const refresh = () => { void loadSurvey().then((data) => { if (active) setSurvey(data); }).catch(() => { if (active) setSurvey(null); }); };
    refresh();
    window.addEventListener('focus', refresh);
    window.addEventListener('perception-survey-updated', refresh);
    return () => { active = false; window.removeEventListener('focus', refresh); window.removeEventListener('perception-survey-updated', refresh); };
  }, [user?.id, user?.role, pathname]);
  const activeSection = getNavigationSection(pathname, user?.role);
  const navigationClass = (section: NavigationSection) =>
    `ui-navigation-link min-w-0 text-center ${activeSection === section ? 'ui-navigation-link--active' : ''}`;

  const handleSignOut = async () => {
    await fetch(`${API_URL}/auth/logout`, {method: 'POST', credentials: 'include', headers: getAuthHeaders()})
      .catch(() => undefined);
    // Clear access token
    Cookies.remove('access_token');

    // Use UserContext signOut to clear language storage and user data
    signOut();

    // Navigate to home
    navigate(ROUTES.welcome);
  };


  return (
    <header
      className="app-header app-header--navigation sticky top-0 z-50 flex w-full min-w-0 shrink-0 flex-wrap items-center gap-layout border-b border-neutral-200 bg-white px-inset py-inset text-neutral-800 lg:grid lg:grid-cols-header lg:items-end"
    >
      <div className="flex min-w-0 flex-1 items-center gap-layout lg:justify-self-start">
        <img
          src={logoDisc}
          alt="Logo"
          className="header-logo block max-w-full"
        />
      </div>
      <nav className="ui-navigation order-3 flex w-full min-w-0 flex-wrap items-center justify-center lg:order-none lg:w-auto">
        <Link
          to={ROUTES.clinicalCases}
          className={navigationClass('cases')}
          aria-current={activeSection === 'cases' ? 'page' : undefined}
        >
          {t('navigation.clinicalCases')}
        </Link>
        <Link
          to={ROUTES.interviews}
          className={navigationClass('interviews')}
          aria-current={activeSection === 'interviews' ? 'page' : undefined}
        >
          {t('navigation.conversations')}
        </Link>
        {user && user.role !== 'superuser' && (survey?.eligible ?
          <Link to={ROUTES.perceptionSurvey} className={`${navigationClass('perception')} relative`} aria-current={activeSection === 'perception' ? 'page' : undefined}>
            {t('perception.title')}{survey.status === 'DRAFT' && <span className="survey-pending" role="img" aria-label={t('perception.pending')} />}
          </Link> :
          <button type="button" className={`${navigationClass('perception')} opacity-50`} disabled title={t('perception.locked')}>{t('perception.title')}</button>)}
        {user?.role === 'superuser' && (
          <Link to={ROUTES.users} className={navigationClass('users')} aria-current={activeSection === 'users' ? 'page' : undefined}>
            {t('navigation.users')}
          </Link>
        )}
      </nav>
      <div className="ui-button-group ui-button-group--large relative ml-auto flex shrink-0 items-center lg:ml-0 lg:justify-self-end">
        <button
          type="button"
          onClick={() => setIsHelpModalOpen(true)}
          className={'header-action'}
          title={t('help.title')}
          aria-label={t('help.title')}
          aria-expanded={isHelpModalOpen}
          aria-haspopup="dialog"
        >
          <Info />
        </button>
        <div className="relative">
          <button
            ref={profileButtonReference}
            type="button"
            onClick={() => setIsMenuOpen((currentValue) => !currentValue)}
            className={'header-action'}
            aria-expanded={isMenuOpen}
            aria-controls={isMenuOpen ? 'profile-menu' : undefined}
            aria-haspopup="true"
            aria-label={t('navigation.profile')}
            title={t('navigation.profile')}
          >
            <CircleUserRound />
          </button>
          <MotionPresence visible={isMenuOpen}>{isMenuOpen && (
            <Menu
              onSignOut={handleSignOut}
              open={isMenuOpen}
              onOutsideClick={() => setIsMenuOpen(false)}
              triggerElement={profileButtonReference.current}
            />
          )}</MotionPresence>
        </div>
      </div>

      {/* Help Modal */}
      <HelpModal
        isOpen={isHelpModalOpen}
        onClose={() => setIsHelpModalOpen(false)}
      />
    </header>
  );
};
