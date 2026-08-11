import i18n from 'i18next';
import {initReactI18next} from 'react-i18next';

// Import translation files
import enTranslations from './locales/en.json';
import esTranslations from './locales/es.json';

const resources = {
  en: {
    translation: enTranslations,
  },
  es: {
    translation: esTranslations,
  },
};

// Initialize i18n with a simpler configuration
i18n
  .use(initReactI18next)
  .init({
    resources,
    lng: 'en',
    fallbackLng: 'en',
    debug: process.env.NODE_ENV === 'development',

    interpolation: {
      escapeValue: false,
    },
  })
  .then(() => {
    console.log('i18n initialized successfully');
    console.log('Available languages after init:', i18n.languages);
    console.log('Current language after init:', i18n.language);

    // Manually set the languages array since i18n.languages is not being populated correctly
    i18n.languages = ['en', 'es'];
  });

export default i18n;
