import {FC} from 'react';
import {useTranslation} from 'react-i18next';

export const Footer: FC = () => {
  const {t} = useTranslation();
  return (
    <footer className="flex w-full min-w-0 flex-col items-center justify-center border-t border-solid border-t-gray-200 bg-white px-4 py-4 text-center">
      <p className="mb-2 text-sm leading-4 text-gray-500 max-sm:text-xs">
        {t('footer.copyright')}
      </p>
      <p className="mb-1 text-sm leading-4 text-gray-500 max-sm:text-xs">
        {t('footer.university')}
      </p>
      <p className="mb-1 text-sm leading-4 text-gray-500 max-sm:text-xs">
        {t('footer.recognition')}
      </p>
      <p className="mb-1 text-sm leading-4 text-gray-500 max-sm:text-xs">
        {t('footer.legalRecognition')}
      </p>
      <p className="mb-1 text-sm leading-4 text-gray-500 max-sm:text-xs">
        {t('footer.address')}
      </p>
      <p className="text-sm leading-4 text-gray-500 max-sm:text-xs">
        <a href="https://sistemas.uniandes.edu.co/es/" target="_blank" rel="noopener noreferrer">
          {t('footer.department')}
        </a>
      </p>
    </footer>
  );
};
