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

export const Header: FC = () => {
  const {pathname} = useLocation();
  const isClinicalRoute = [ROUTES.clinicalChat, ROUTES.createCase].includes(pathname);
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

  return (
    <header
      className="fixed top-0 left-0 flex justify-between items-center px-20 py-4 w-full bg-white border-b-2 border-solid border-b-gray-200 max-md:px-3 max-md:max-w-full"
      style={{zIndex: 1}}
    >
      <div className="flex items-center gap-2">
        <img src={logoDisc} alt="Logo" className="h-14 w-auto" style={{filter: 'invert(1)'}} />
        <LogoIcon />
      </div>
      <nav className="flex ml-auto">
        <NavLink
          to={ROUTES.clinicalCases}
          className={({isActive}) =>
            isActive || isClinicalRoute ? 'bg-blue-100' : 'hover:bg-gray-100'
          }
          style={({isActive}) => ({
            margin: '0 20px 0 0',
            padding: '5px 10px',
            borderRadius: '5px',
            color: isActive || isClinicalRoute ? '#155dfc' : '#515151',
            fontSize: '16px',
            fontWeight: 600,
            fontFamily: 'Arial',
          })}
        >
          {t('navigation.clinicalCases')}
        </NavLink>
        <NavLink
          to={ROUTES.conversations}
          className={({isActive}) => (isActive ? 'bg-blue-100' : 'hover:bg-gray-100')}
          style={({isActive}) => ({
            margin: '0 20px 0 0',
            padding: '5px 10px',
            borderRadius: '5px',
            color: isActive ? '#155dfc' : '#515151',
            fontSize: '16px',
            fontWeight: 600,
            fontFamily: 'Arial',
          })}
        >
          {t('navigation.conversations')}
        </NavLink>
        {(user?.role === 'teacher' || user?.role === 'superuser') && (
          <NavLink
            to={ROUTES.students}
            className={({isActive}) => (isActive ? 'bg-blue-100' : 'hover:bg-gray-100')}
            style={({isActive}) => ({
              margin: '0 20px 0 0',
              padding: '5px 10px',
              borderRadius: '5px',
              color: isActive ? '#155dfc' : '#515151',
              fontSize: '16px',
              fontWeight: 600,
              fontFamily: 'Arial',
            })}
          >
            {t('navigation.students')}
          </NavLink>
        )}
      </nav>
      <div className="relative flex gap-6 items-center">
        <LanguageSwitcher />
        <button
          onClick={() => setIsHelpModalOpen(true)}
          className="cursor-pointer hover:opacity-70 transition-opacity"
          title={t('help.title')}
        >
          <HelpIcon />
        </button>
        <div className="relative">
          <span onClick={() => setIsMenuOpen(!isMenuOpen)} className="cursor-pointer">
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
