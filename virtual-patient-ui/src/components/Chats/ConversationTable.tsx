import {InterviewDeleteDialog} from './InterviewDeleteDialog';
import {LIST_PAGE_SIZE as ITEMS_PER_PAGE} from '../../utils/pagination';
import {useEffect, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {ListPanel, Pagination} from '../common';
import {TableHeader} from '../common/Table/TableHeader';
import {useSessionList} from '../../contexts/SessionLists';
import {ConversationTableRow} from './ConversationTableRow';
import {TableLoadingRows} from '../common/Table/TableLoadingState';
import {deleteInterview} from '../../services/interviews';

export const ConversationTable = () => {
  const {t} = useTranslation();
  const [currentPage, setCurrentPage] = useState(1);
  const [interviewToDelete, setInterviewToDelete] = useState<number | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const COLUMN_HEADERS = [
    'ID',
    t('conversations.date'),
    t('conversations.clinicalCase'),
    t('conversations.duration'),
    t('conversations.status'),
    t('conversations.score'),
    t('conversations.action'),
  ] as const;

  const {items, loading, error, load} = useSessionList('interviews');
  const page = Math.min(currentPage, Math.max(1, Math.ceil((items?.length ?? 0) / ITEMS_PER_PAGE)));
  const pageStartIndex = (page - 1) * ITEMS_PER_PAGE;
  const interviews = items?.slice(pageStartIndex, pageStartIndex + ITEMS_PER_PAGE) ?? [];
  const hasNext = pageStartIndex + ITEMS_PER_PAGE < (items?.length ?? 0);
  const isLoading = loading && items === undefined;
  useEffect(() => {
    if (loading || isDeleting || error || !items?.some(({status}) => status === 'processing' || status === 'in_progress')) return;
    const timer = window.setTimeout(() => void load(true), 5000);
    return () => window.clearTimeout(timer);
  }, [error, isDeleting, items, load, loading]);
  const confirmDelete = async () => {
    if (interviewToDelete === null || isDeleting) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await deleteInterview(interviewToDelete);
      setInterviewToDelete(null);
      await load(true);
    } catch {
      setDeleteError(t('conversations.deleteFailed'));
    } finally {
      setIsDeleting(false);
    }
  };

  const renderTableControls = () => (
    <Pagination
      page={page}
      onPageChange={setCurrentPage}
      hasNext={hasNext}
      totalPages={Math.max(1, Math.ceil((items?.length ?? 0) / ITEMS_PER_PAGE))}
      disabled={isLoading}
      label={t('conversations.myConversationHistory')}
      description={t('pagination.showing', {
        from: interviews.length > 0 ? pageStartIndex + 1 : 0,
        to: pageStartIndex + interviews.length,
        total: items?.length ?? 0,
      })}
    />
  );

  return (
    <ListPanel titleId="interviews-title" pagination={renderTableControls()}>
      {error && (
        <div className="ui-panel-body" role="alert">
          {t('errors.generic')}{' '}
          <button type="button" className="ui-action-text" onClick={() => void load(true)}>
            {t('common.retry')}
          </button>
        </div>
      )}
      <div className="ui-table-scroll" tabIndex={0} aria-busy={isLoading}>
        <table className="ui-data-table ui-data-table--scrollable">
          <caption className="sr-only">{t('conversations.myConversationHistory')}</caption>
          <TableHeader columns={COLUMN_HEADERS} hideLastLabel />
          <tbody>
            {isLoading && !interviews.length ? (
              <TableLoadingRows columns={COLUMN_HEADERS} stackedColumns={[1, 2]} actionCount={1} />
            ) : interviews.length === 0 && !error ? (
              <tr>
                <td colSpan={7} className="px-layout py-layout text-center text-neutral-500">
                  {t('conversations.noConversations')}
                </td>
              </tr>
            ) : (
              interviews.map((interview) => (
                <ConversationTableRow
                  key={interview.publicId}
                  id={String(interview.id)}
                  createdAt={interview.createdAt}
                  startTime={interview.startTime}
                  status={interview.status}
                  canRetryCompletion={interview.interviewMetadata?.completionProcessing?.status === 'failed'}
                  duration={interview.totalDuration}
                  clinicalCase={interview.clinicalCase}
                  score={interview.evaluationScore}
                  personality={interview.personality}
                  isAssigned={interview.isAssigned}
                  manualRatingStatus={interview.manualRatingStatus}
                  onDelete={(id) => {
                    setDeleteError(null);
                    setInterviewToDelete(id);
                  }}
                />
              ))
            )}
          </tbody>
        </table>
      </div>
      <InterviewDeleteDialog
        interviewId={interviewToDelete}
        busy={isDeleting}
        error={deleteError}
        onCancel={() => {
          if (!isDeleting) setInterviewToDelete(null);
        }}
        onConfirm={() => void confirmDelete()}
      />
    </ListPanel>
  );
};
