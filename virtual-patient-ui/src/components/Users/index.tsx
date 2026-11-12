import {Badge} from '../common/Badge';
import {DateTime} from '../common/DateTime';
import {AdministrativeDeleteDialog} from '../common/AdministrativeDeleteDialog';
import {useEffect, useState} from 'react';
import {Navigate, useNavigate} from 'react-router-dom';
import {useTranslation} from 'react-i18next';
import {useSessionList} from '../../hooks/useSessionList';
import {useUser} from '../../hooks/useUser';
import {ROUTES} from '../../utils/routes';
import {User} from '../../types/user';
import {Button, ListPanel, Pagination} from '../common';
import {UserEditor} from './UserEditor';
import {useManagedUsers} from './useManagedUsers';
import {MotionPresence} from '../common/Motion';
import {TableLoadingState} from '../common/Table/TableLoadingState';
import {PageHeader} from '../common/PageHeader';
import {ClipboardList, MessageSquareText, Trash2} from 'lucide-react';
import {getManagedActivity, ManagedActivity} from '../../services/users/manageUsers';
import {SubmittedSurveyDialog} from './SubmittedSurveyDialog';

export const Users = () => {
  const {user, isLoading} = useUser();
  const {t} = useTranslation();
  const navigate = useNavigate();
  const {users, total, offset, loading, error, reload, setOffset, pageSize} = useManagedUsers(
    user?.role === 'admin',
  );
  const {load: refreshHistory} = useSessionList('adminHistory', false);
  const columnHeaders = [
    'users.registeredAt',
    'auth.name',
    'auth.email',
    'auth.role',
    'users.actions',
  ];
  const [editor, setEditor] = useState<{account?: User} | null>(null);
  const [notice, setNotice] = useState('');
  const [deleting, setDeleting] = useState<User | null>(null);
  const [surveyAccount, setSurveyAccount] = useState<User | null>(null);
  const [activity, setActivity] = useState<ManagedActivity[]>([]);
  const [activityError, setActivityError] = useState(false);
  const [activityVersion, setActivityVersion] = useState(0);
  useEffect(() => {
    if (user?.role !== 'admin') return;
    let active = true;
    setActivityError(false);
    void getManagedActivity().then((result) => {
      if (active) setActivity(result);
    }).catch(() => {
      if (active) {
        setActivity([]); setActivityError(true);
      }
    });
    return () => {
      active = false;
    };
  }, [user?.id, user?.role, activityVersion]);
  if (isLoading) return <p role="status">{t('common.loading')}</p>;
  if (user?.role !== 'admin') return <Navigate to={ROUTES.home} replace />;
  return (
    <section className="ui-page" aria-labelledby="users-title">
      <PageHeader
        eyebrow={t('users.pageEyebrow')}
        title={t('users.pageTitle')}
        titleId="users-title"
      >
        <div className="ui-button-group ui-button-group--large">
          <Button
            onClick={() => {
              setNotice('');
              setEditor({});
            }}
          >
            {t('users.create')}
          </Button>
        </div>
      </PageHeader>
      {notice && (
        <p className="ui-notice ui-notice--success" role="status">
          {t(notice)}
        </p>
      )}
      {activityError && <div role="alert" className="ui-notice ui-notice--warning">
        {t('users.activityError')} <Button variant="text" onClick={() => setActivityVersion((value) => value + 1)}>{t('common.retry')}</Button>
      </div>}
      <ListPanel
        titleId="users-title"
        pagination={
          <Pagination
            page={offset / pageSize + 1}
            onPageChange={(page) => setOffset((page - 1) * pageSize)}
            label={t('users.accounts')}
            disabled={loading}
            hasNext={!error && offset + users.length < total}
            totalPages={Math.max(1, Math.ceil(total / pageSize))}
            description={t('pagination.showingUsers', {
              from: users.length ? offset + 1 : 0,
              to: offset + users.length,
              total,
            })}
          />
        }
      >
        {error && users.length > 0 && (
          <div className="ui-notice ui-notice--danger" role="alert">
            {t(error, {defaultValue: t('errors.generic')})}
            <Button variant="text" onClick={() => reload()}>
              {t('common.retry')}
            </Button>
          </div>
        )}
        {error && users.length === 0 ? (
          <div className="ui-empty-state">
            <p role="alert">{t(error, {defaultValue: t('errors.generic')})}</p>
            <Button variant="secondary" onClick={() => reload()}>
              {t('common.retry')}
            </Button>
          </div>
        ) : loading && users.length === 0 ? (
          <TableLoadingState
            columns={columnHeaders.map((key) => t(key))}
            stackedColumns={[0]}
            actionCount={3}
            label={t('common.loading')}
          />
        ) : (
          <div aria-busy={loading}>
            <div className="ui-table-scroll" tabIndex={0}>
              <table className="ui-data-table ui-data-table--scrollable">
                <caption className="sr-only">{t('users.accounts')}</caption>
                <thead>
                  <tr>
                    {columnHeaders.map((label) => (
                      <th scope="col" key={label}>
                        {label === 'users.actions' ? (
                          <span className="sr-only">{t(label)}</span>
                        ) : (
                          t(label)
                        )}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {users.length === 0 ? (
                    <tr>
                      <td colSpan={columnHeaders.length} className="text-center">
                        {t('users.empty')}
                      </td>
                    </tr>
                  ) : users.map((account) => (
                    <tr key={account.id} className={!loading && !error ? 'ui-interactive-row' : undefined}
                      tabIndex={!loading && !error ? 0 : undefined}
                      aria-label={t('users.editAccount', {name: account.name})}
                      onClick={() => {
                        if (loading || error) return;
                        setNotice('');
                        setEditor({account});
                      }}
                      onKeyDown={(event) => {
                        if (event.target === event.currentTarget && (event.key === 'Enter' || event.key === ' ')) {
                          event.preventDefault();
                          event.currentTarget.click();
                        }
                      }}>
                      <td>
                        <DateTime value={account.createdAt} fallback={t('users.dateUnavailable')} />
                      </td>
                      <th scope="row">{account.name}</th>
                      <td className="ui-email-cell">{account.email}</td>
                      <td>
                        <Badge tone="info">{t('common.' + account.role)}</Badge>
                      </td>
                      <td>
                        <div className="ui-table-options ui-table-options--icons">
                          <Button variant="secondary" className="ui-icon-button"
                            disabled={loading || Boolean(error) || !activity.find((item) => item.userId === account.id)?.hasInterviews}
                            aria-label={t('users.viewInterviews')} title={t('users.viewInterviews')}
                            onClick={(event) => {
                              event.stopPropagation(); navigate(`${ROUTES.interviews}?user=${account.id}`, {state: {accountName: account.name}});
                            }}>
                            <MessageSquareText aria-hidden="true" />
                          </Button>
                          <Button variant="secondary" className="ui-icon-button"
                            disabled={loading || Boolean(error) || !activity.find((item) => item.userId === account.id)?.hasSubmittedSurvey}
                            aria-label={t('users.viewSurvey')} title={t('users.viewSurvey')}
                            onClick={(event) => {
                              event.stopPropagation(); setSurveyAccount(account);
                            }}>
                            <ClipboardList aria-hidden="true" />
                          </Button>
                          <Button
                            variant="secondary"
                            className="ui-icon-button ui-button--hover-danger"
                            disabled={loading || Boolean(error)}
                            aria-label={t('common.delete')}
                            title={t('common.delete')}
                            onClick={(event) => {
                              event.stopPropagation();
                              setDeleting(account);
                            }}
                          >
                            <Trash2 aria-hidden="true" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </ListPanel>
      <MotionPresence visible={Boolean(deleting)}>
        {deleting && (
          <AdministrativeDeleteDialog
            path={'/users/admin/' + deleting.id}
            name={deleting.name}
            onClose={() => setDeleting(null)}
            onDeleted={() => {
              setDeleting(null);
              reload();
              setActivityVersion((value) => value + 1);
              void refreshHistory(true);
            }}
          />
        )}
      </MotionPresence>
      <MotionPresence visible={Boolean(editor)}>
        {editor && (
          <UserEditor
            account={editor.account}
            onClose={() => setEditor(null)}
            onSaved={(created) => {
              setEditor(null);
              setNotice(created ? 'users.created' : 'users.updated');
              reload(created);
              setActivityVersion((value) => value + 1);
              if (!created) void refreshHistory(true);
            }}
          />
        )}
      </MotionPresence>
      <MotionPresence visible={Boolean(surveyAccount)}>
        {surveyAccount && <SubmittedSurveyDialog account={surveyAccount} onClose={() => setSurveyAccount(null)} />}
      </MotionPresence>
    </section>
  );
};

