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
      console.log('Initializing language from user data:', user.preferredLanguage);
      setCurrentLanguage(user.preferredLanguage);
    }
  }, [user?.preferredLanguage]);

  // Update current language when i18n language changes
  useEffect(() => {
    const handleLanguageChange = (lng: string) => {
      console.log('Language changed event received:', lng);
      setCurrentLanguage(lng);
    };

    i18n.on('languageChanged', handleLanguageChange);
    console.log('Current language state:', currentLanguage, 'i18n language:', i18n.language);

    return () => {
      i18n.off('languageChanged', handleLanguageChange);
    };
  }, [i18n, currentLanguage]);

  const changeLanguage = async (language: string) => {
    await updateUserLanguage(language);
  };

  return (
    <div className="flex items-center gap-2">
      <Button
        onClick={() => changeLanguage('en')}
        variant={currentLanguage === 'en' ? 'primary' : 'secondary'}
        size="sm"
      >
        EN
      </Button>
      <Button
        onClick={() => changeLanguage('es')}
        variant={currentLanguage === 'es' ? 'primary' : 'secondary'}
        size="sm"
      >
        ES
      </Button>
    </div>
  );
};
