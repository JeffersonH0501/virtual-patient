import {FC, useState} from 'react';
import {LogoIcon, HelpIcon, ProfileIcon} from '../../../icons/';
import {NavLink, useLocation, useNavigate} from 'react-router-dom';
import {ROUTES} from '../../../utils/routes';
import {Menu} from '../Menu';
import {LanguageSwitcher} from '../LanguageSwitcher';
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
  const isClinicalChat = pathname.startsWith(`${ROUTES.clinicalChat}/`);
  const isClinicalRoute =
    pathname.startsWith(`${ROUTES.clinicalChat}/`) || pathname === ROUTES.createCase;
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isHelpModalOpen, setIsHelpModalOpen] = useState(false);
  const navigate = useNavigate();
  const {t} = useTranslation();
  const {user, signOut} = useUser();

  const handleSignOut = () => {
    // Clear access token
    Cookies.remove('access_token');

    // Use UserContext signOut to clear language storage and user data
    signOut();

    // Navigate to home
    navigate(ROUTES.home);
  };

  if (isClinicalChat && clinicalSimulationActive) {
    return (
      <header className="sticky top-0 z-50 flex w-full min-w-0 shrink-0 items-center gap-3 border-b border-gray-200 bg-white px-3 py-2.5 sm:px-6 lg:px-10 lg:py-3">
        <div className="flex min-w-0 items-center gap-2">
          <img
            src={logoDisc}
            alt="Logo"
            className="h-7 w-auto sm:h-10 lg:h-12"
            style={{filter: 'invert(1)'}}
          />
          <span className="hidden md:block">
            <LogoIcon />
          </span>
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
      className="sticky top-0 z-50 flex w-full min-w-0 shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b border-gray-200 bg-white px-3 py-2.5 sm:px-6 lg:flex-nowrap lg:px-20 lg:py-4"
    >
      <div className="flex min-w-0 items-center gap-2">
        <img
          src={logoDisc}
          alt="Logo"
          className="h-9 w-auto sm:h-11 lg:h-14"
          style={{filter: 'invert(1)'}}
        />
        <span className="hidden xl:block">
          <LogoIcon />
        </span>
      </div>
      <nav className="order-3 flex w-full min-w-0 items-center justify-center gap-1 border-t border-slate-100 pt-2 lg:order-none lg:ml-auto lg:w-auto lg:border-0 lg:pt-0">
        <NavLink
          to={ROUTES.clinicalCases}
          style={({isActive}) => ({color: isActive || isClinicalRoute ? '#155dfc' : '#515151'})}
          className={({isActive}) =>
            `min-w-0 rounded-md px-3 py-2 text-center text-sm font-semibold leading-5 lg:px-4 lg:text-base ${
              isActive || isClinicalRoute ? 'bg-blue-100' : 'hover:bg-gray-100'
            }`
          }
        >
          {t('navigation.clinicalCases')}
        </NavLink>
        <NavLink
          to={ROUTES.conversations}
          className={({isActive}) =>
            `min-w-0 rounded-md px-3 py-2 text-center text-sm font-semibold leading-5 lg:px-4 lg:text-base ${
              isActive ? 'bg-blue-100' : 'hover:bg-gray-100'
            }`
          }
          style={({isActive}) => ({color: isActive ? '#155dfc' : '#515151'})}
        >
          {t('navigation.conversations')}
        </NavLink>
        {(user?.role === 'teacher' || user?.role === 'superuser') && (
          <NavLink
            to={ROUTES.students}
            className={({isActive}) =>
              `min-w-0 rounded-md px-2 py-2 text-center text-sm font-semibold leading-5 lg:px-4 lg:text-base ${
                isActive ? 'bg-blue-100' : 'hover:bg-gray-100'
              }`
            }
            style={({isActive}) => ({color: isActive ? '#155dfc' : '#515151'})}
          >
            {t('navigation.students')}
          </NavLink>
        )}
      </nav>
      <div className="relative ml-auto flex shrink-0 items-center gap-2 sm:gap-4 lg:gap-6">
        <LanguageSwitcher />
        <button
          onClick={() => setIsHelpModalOpen(true)}
          className="hidden cursor-pointer p-1 transition-opacity hover:opacity-70 sm:block"
          title={t('help.title')}
        >
          <HelpIcon />
        </button>
        <div className="relative">
          <span onClick={() => setIsMenuOpen(!isMenuOpen)} className="block cursor-pointer p-1">
            <ProfileIcon />
          </span>
          {isMenuOpen && (
            <Menu
              onSignOut={handleSignOut}
              open={isMenuOpen}
              onOutsideClick={() => setIsMenuOpen(false)}
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
