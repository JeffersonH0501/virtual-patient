import {FC} from 'react';
import {useTranslation} from 'react-i18next';

export const Footer: FC = () => {
  const {t} = useTranslation();
  return (
    <footer className="flex w-full min-w-0 shrink-0 flex-col items-center justify-center border-t border-solid border-t-neutral-200 bg-white px-inset py-inset text-center">
      <p className="text-neutral-500 default-text">
        {t('footer.copyright')}
        <br />
        {t('footer.university')}
        <br />
        {t('footer.recognition')}
        <br />
        {t('footer.legalRecognition')}
        <br />
        {t('footer.address')}
        <br />
        <a href="https://sistemas.uniandes.edu.co/es/" target="_blank" rel="noopener noreferrer">
          {t('footer.department')}
        </a>
      </p>
    </footer>
  );
};
