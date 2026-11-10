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
    lng: 'es',
    fallbackLng: 'en',
    debug: import.meta.env.DEV,

    interpolation: {
      escapeValue: false,
    },
  })
  .then(() => {

    // Manually set the languages array since i18n.languages is not being populated correctly
    i18n.languages = ['en', 'es'];
  });

export default i18n;
