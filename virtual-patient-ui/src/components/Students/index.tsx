import {useUser} from '../../hooks/useUser';
import {StudentsTable} from './StudentsTable';
import {Navigate} from 'react-router-dom';
import {useTranslation} from 'react-i18next';
import {ROUTES} from '../../utils/routes';
import {PageHeader} from '../common/PageHeader';

export const Students = () => {
  const {user} = useUser();
  const {t} = useTranslation();
  if (user?.role === 'teacher') return <Navigate to={ROUTES.interviews} replace />;
  return (
    <section className="ui-page">
      <PageHeader eyebrow={t('interviewsPage.eyebrow')} title={t('interviewsPage.title')} titleId="interviews-title" />
      <StudentsTable />
    </section>
  );
};
