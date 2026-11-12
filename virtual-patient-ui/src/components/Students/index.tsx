import {useUser} from '../../hooks/useUser';
import {StudentsTable} from './StudentsTable';
import {Navigate, useLocation, useSearchParams} from 'react-router-dom';
import {useTranslation} from 'react-i18next';
import {ROUTES} from '../../utils/routes';
import {PageHeader} from '../common/PageHeader';
import {Badge} from '../common/Badge';
import {X} from 'lucide-react';
import {useSessionList} from '../../hooks/useSessionList';
import {ManagedInterviews} from '../Users/ManagedInterviews';

export const Students = () => {
  const {user} = useUser();
  const {t} = useTranslation();
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const id = Number(params.get('user'));
  const userId = Number.isSafeInteger(id) && id > 0 ? id : null;
  const {items: users} = useSessionList('users', user?.role === 'admin' && userId !== null);
  const name = users?.find((item) => item.id === userId)?.name ?? (typeof location.state?.accountName === 'string' ? location.state.accountName : '');
  if (user?.role === 'doctor') return <Navigate to={ROUTES.interviews} replace />;
  return (
    <section className="ui-page">
      <PageHeader eyebrow={t('interviewsPage.eyebrow')} title={t('interviewsPage.title')} titleId="interviews-title">
        {userId && <Badge tone="info" className="gap-2">
          {name ? t('users.namedInterviews', {name}) : t('users.userInterviews')}
          <button type="button" aria-label={t('users.clearInterviewFilter')} title={t('users.clearInterviewFilter')}
            onClick={() => {
              const next = new URLSearchParams(params); next.delete('user'); setParams(next);
            }}>
            <X aria-hidden="true" size={16} />
          </button>
        </Badge>}
      </PageHeader>
      {userId ? <ManagedInterviews key={userId} userId={userId} /> : <StudentsTable />}
    </section>
  );
};
