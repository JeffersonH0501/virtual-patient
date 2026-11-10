import { FC } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { NonIdealState } from '../common/NonIdealState';
import { ROUTES } from '../../utils/routes';
import {TriangleAlert} from 'lucide-react';

export const TokenExpiredScreen: FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <NonIdealState
      title={t('errors.sessionExpired')}
      description={t('errors.sessionExpiredDescription')}
      icon={
        <span className="block h-16 w-16 [&_svg]:h-full [&_svg]:w-full">
          <TriangleAlert />
        </span>
      }
      action={{
        label: t('errors.goToLogin'),
        onClick: () => navigate(ROUTES.welcome),
      }}
      className="min-h-screen bg-neutral-50"
    />
  );
};
