import {useTranslation} from 'react-i18next';

export const InterviewContentLoading = () => {
  const {t} = useTranslation();
  return <p role="status" aria-label={t('common.loading')} aria-busy="true" className="p-layout">{t('common.loading')}</p>;
};
