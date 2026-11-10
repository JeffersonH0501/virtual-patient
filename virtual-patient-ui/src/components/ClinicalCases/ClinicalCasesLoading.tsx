import {useTranslation} from 'react-i18next';

export const ClinicalCasesLoading = () => {
  const {t} = useTranslation();
  return <p role="status">{t('common.loading')}</p>;
};
