import {FC, useRef, useState} from 'react';
import {Info, UserCircle} from '../../../icons/';
import {NavLink, useLocation, useNavigate, matchPath} from 'react-router-dom';
import {ROUTES} from '../../../utils/routes';
import {Menu} from '../Menu';
import {HelpModal} from '../HelpModal';
import logoDisc from '/src/assets/logo_disc.png';
import Cookies from 'js-cookie';
import {useTranslation} from 'react-i18next';
import {useUser} from '../../../hooks';

type HeaderProps = {
  clinicalSimulationActive?: boolean;
};

export const Header: FC<HeaderProps> = ({clinicalSimulationActive = false}) => {
  const {pathname} = useLocation();
  const isClinicalChat = Boolean(matchPath(ROUTES.interviewSession, pathname) || matchPath(ROUTES.interviewReview, pathname));
  const isClinicalRoute =
    pathname === ROUTES.createCase;
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isHelpModalOpen, setIsHelpModalOpen] = useState(false);
  const profileButtonReference = useRef<HTMLButtonElement>(null);
  const navigate = useNavigate();
  const {t} = useTranslation();
  const {user, signOut} = useUser();

  const handleSignOut = () => {
    // Clear access token
    Cookies.remove('access_token');

    // Use UserContext signOut to clear language storage and user data
    signOut();

    // Navigate to home
    navigate(ROUTES.signIn);
  };

  if (isClinicalChat && clinicalSimulationActive) {
    return (
      <header className="sticky top-0 z-50 flex w-full min-w-0 shrink-0 items-center gap-3 border-b border-gray-200 bg-white px-3 py-2.5 text-slate-800 sm:px-6 lg:px-10 lg:py-3">
        <div className="flex min-w-0 items-center gap-2">
          <img
            src={logoDisc}
            alt="Logo"
            className="header-logo h-7 w-auto sm:h-10 lg:h-12"
          />
        </div>
        <div
          id="clinical-call-header-controls"
          className="ml-auto flex min-w-0 items-center justify-end"
        />
      </header>
    );
  }

  return (
    <header
      className="sticky top-0 z-50 flex w-full min-w-0 shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b border-gray-200 bg-white px-3 py-2.5 text-slate-800 sm:px-6 lg:grid lg:grid-cols-header lg:px-20 lg:py-4"
    >
      <div className="flex min-w-0 items-center gap-2 lg:justify-self-start">
        <img
          src={logoDisc}
          alt="Logo"
          className="header-logo h-9 w-auto sm:h-11 lg:h-14"
        />
      </div>
      <nav className="order-3 grid w-full min-w-0 auto-cols-fr grid-flow-col items-stretch justify-center gap-1 border-t border-slate-100 pt-2 lg:order-none lg:w-auto lg:border-0 lg:pt-0">
        <NavLink
          to={ROUTES.clinicalCases}
          className={({isActive}) =>
            `header-navigation-link w-full min-w-0 rounded-md text-center text-sm font-semibold leading-5 lg:text-base ${
              isActive || isClinicalRoute
                ? 'bg-blue-100 text-blue-600'
                : 'text-slate-800 hover:bg-slate-100 hover:text-brand-600'
            }`
          }
        >
          {t('navigation.clinicalCases')}
        </NavLink>
        {user?.role !== 'superuser' && (
          <NavLink
            to={ROUTES.interviews}
            className={({isActive}) =>
              `header-navigation-link w-full min-w-0 rounded-md text-center text-sm font-semibold leading-5 lg:text-base ${
                isActive
                  ? 'bg-blue-100 text-blue-600'
                  : 'text-slate-800 hover:bg-slate-100 hover:text-brand-600'
              }`
            }
          >
            {t('navigation.conversations')}
          </NavLink>
        )}
        {(user?.role === 'teacher' || user?.role === 'superuser') && (
          <NavLink
            to={ROUTES.students}
            className={({isActive}) =>
              `header-navigation-link w-full min-w-0 rounded-md text-center text-sm font-semibold leading-5 lg:text-base ${
                isActive
                  ? 'bg-blue-100 text-blue-600'
                  : 'text-slate-800 hover:bg-slate-100 hover:text-brand-600'
              }`
            }
          >
            {t('navigation.students')}
          </NavLink>
        )}
      </nav>
      <div className="relative ml-auto flex shrink-0 items-start gap-0 lg:ml-0 lg:justify-self-end">
        <button
          type="button"
          onClick={() => setIsHelpModalOpen(true)}
          className={'hidden sm:flex header-action'}
          title={t('help.title')}
          aria-label={t('help.title')}
        >
          <Info />
          <span className="-mt-0.5 text-xs font-semibold leading-4">{t('navigation.help')}</span>
        </button>
        <div className="relative">
          <button
            ref={profileButtonReference}
            type="button"
            onClick={() => setIsMenuOpen((currentValue) => !currentValue)}
            className={'flex header-action'}
            aria-expanded={isMenuOpen}
            aria-label={t('navigation.profile')}
          >
            <UserCircle />
            <span className="-mt-0.5 text-xs font-semibold leading-4">{t('navigation.profile')}</span>
          </button>
          {isMenuOpen && (
            <Menu
              onSignOut={handleSignOut}
              open={isMenuOpen}
              onOutsideClick={() => setIsMenuOpen(false)}
              triggerElement={profileButtonReference.current}
            />
          )}
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
