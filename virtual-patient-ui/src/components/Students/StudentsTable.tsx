import {useEffect, useRef, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Button, ListPanel, Pagination} from '../common';
import {TableHeader} from '../common/Table/TableHeader';
import {useSessionList} from '../../contexts/SessionLists';
import {StudentsTableRow} from './StudentsTableRow';
import {LIST_PAGE_SIZE} from '../../utils/pagination';
import {useUser} from '../../hooks/useUser';
import {deleteInterview} from '../../services/interviews';
import {InterviewDeleteDialog} from '../Chats/InterviewDeleteDialog';
import {TableLoadingState} from '../common/Table/TableLoadingState';

export const StudentsTable = () => {
  const {t} = useTranslation();
  const {user} = useUser();
  const [requestedPage, setRequestedPage] = useState(1);
  const [interviewToDelete, setInterviewToDelete] = useState<number | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const deleting = useRef(false);
  const organizationId = user?.organizationId;
  const columnHeaders = [
    'ID',
    t('conversations.date'),
    t('students.participant'),
    t('conversations.clinicalCase'),
    t('students.duration'),
    t('students.status'),
    t('students.score'),
    t('conversations.action'),
  ];
  const {items, loading, error, load} = useSessionList('organization', organizationId != null, organizationId);
  const total = items?.length ?? 0;
  const currentPage = Math.min(requestedPage, Math.max(1, Math.ceil(total / LIST_PAGE_SIZE)));
  const offset = (currentPage - 1) * LIST_PAGE_SIZE;
  const interviews = items?.slice(offset, offset + LIST_PAGE_SIZE) ?? [];
  const isLoading = loading && items === undefined;
  const busy = isLoading;
  useEffect(() => {
    if (loading || isDeleting || error || !items?.some(({status}) => status === 'processing')) return;
    const timer = window.setTimeout(() => void load(true), 5000);
    return () => window.clearTimeout(timer);
  }, [error, isDeleting, items, load, loading]);

  const confirmDelete = async () => {
    if (interviewToDelete === null || deleting.current) return;
    deleting.current = true;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await deleteInterview(interviewToDelete);
      setInterviewToDelete(null);
      await load(true);
    } catch (failure) {
      console.error('Failed to delete organization interview:', failure);
      setDeleteError(t('conversations.deleteFailed'));
    } finally {
      deleting.current = false;
      setIsDeleting(false);
    }
  };
  return (
    <ListPanel
      titleId="interviews-title"
      pagination={
        <Pagination
          page={currentPage}
          onPageChange={setRequestedPage}
          totalPages={Math.max(1, Math.ceil(total / LIST_PAGE_SIZE))}
          hasNext={currentPage * LIST_PAGE_SIZE < total && !error}
          disabled={busy || isDeleting || !!error}
          label={t('students.history')}
          description={t('pagination.showing', {
            from: interviews.length ? (currentPage - 1) * LIST_PAGE_SIZE + 1 : 0,
            to: interviews.length ? (currentPage - 1) * LIST_PAGE_SIZE + interviews.length : 0,
            total,
          })}
        />
      }
    >
      {error && interviews.length > 0 && (
        <div className="ui-notice ui-notice--danger" role="alert">
          {t('errors.generic')}
          <Button variant="text" onClick={() => void load(true)}>
            {t('common.retry')}
          </Button>
        </div>
      )}
      {isLoading && interviews.length === 0 ? (
        <TableLoadingState columns={columnHeaders} stackedColumns={[1, 2, 3]} actionCount={1} label={t('common.loading')} />
      ) : error && interviews.length === 0 ? (
        <div className="ui-empty-state">
          <p role="alert" className="text-danger-700">
            {t('errors.generic')}
          </p>
          <Button
            variant="secondary"
            onClick={() => void load(true)}
          >
            {t('common.retry')}
          </Button>
        </div>
      ) : (
        <div aria-busy={busy}>
          <div className="ui-table-scroll" tabIndex={0}>
            <table className="ui-data-table">
              <caption className="sr-only">{t('students.history')}</caption>
              <TableHeader columns={columnHeaders} hideLastLabel />
              <tbody>
                {interviews.length === 0 ? (
                  <tr>
                    <td colSpan={columnHeaders.length} className="text-center">
                      {t('students.noInterviews')}
                    </td>
                  </tr>
                ) : (
                  interviews.map((interview) => (
                    <StudentsTableRow
                      key={interview.id}
                      interview={interview}
                      busy={busy || isDeleting || Boolean(error)}
                      canDelete={user?.role === 'superuser' || user?.id === interview.userId}
                      onDelete={() => {
                        setDeleteError(null);
                        setInterviewToDelete(interview.id);
                      }}
                    />
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
      <InterviewDeleteDialog
        interviewId={interviewToDelete}
        busy={isDeleting}
        error={deleteError}
        onCancel={() => {
          if (!deleting.current) setInterviewToDelete(null);
        }}
        onConfirm={() => void confirmDelete()}
      />
    </ListPanel>
  );
};
