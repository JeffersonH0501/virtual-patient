import {FC, useEffect, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Button} from '../Button';
import {useUser} from '../../../hooks';
import {getStoredLanguage} from '../../../utils/languageStorage';

export const LanguageSwitcher: FC = () => {
  const {i18n} = useTranslation();
  const {updateUserLanguage, user} = useUser();
  const [currentLanguage, setCurrentLanguage] = useState(getStoredLanguage());

  // Initialize language from user data if available
  useEffect(() => {
    if (user?.preferredLanguage) {
      setCurrentLanguage(user.preferredLanguage);
    }
  }, [user?.preferredLanguage]);

  // Update current language when i18n language changes
  useEffect(() => {
    const handleLanguageChange = (lng: string) => {
      setCurrentLanguage(lng);
    };

    i18n.on('languageChanged', handleLanguageChange);

    return () => {
      i18n.off('languageChanged', handleLanguageChange);
    };
  }, [i18n, currentLanguage]);

  const changeLanguage = async (language: string) => {
    await updateUserLanguage(language);
  };

  return (
    <div className="ui-button-group flex items-center">
      <Button
        onClick={() => changeLanguage('en')}
        variant={currentLanguage === 'en' ? 'primary' : 'secondary'}
        aria-pressed={currentLanguage === 'en'}
      >
        EN
      </Button>
      <Button
        onClick={() => changeLanguage('es')}
        variant={currentLanguage === 'es' ? 'primary' : 'secondary'}
        aria-pressed={currentLanguage === 'es'}
      >
        ES
      </Button>
    </div>
  );
};
