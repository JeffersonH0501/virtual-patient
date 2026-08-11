import { FC } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { NonIdealState } from '../common/NonIdealState';
import { ROUTES } from '../../utils/routes';

export const TokenExpiredScreen: FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <NonIdealState
      title={t('errors.sessionExpired')}
      description={t('errors.sessionExpiredDescription')}
      icon={
        <svg className="w-16 h-16" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.732-.833-2.5 0L4.268 19.5c-.77.833.192 2.5 1.732 2.5z" />
        </svg>
      }
      action={{
        label: t('errors.goToLogin'),
        onClick: () => navigate(ROUTES.home)
      }}
      className="min-h-screen bg-gray-50"
    />
  );
};
