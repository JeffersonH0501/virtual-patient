import {useEffect, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Modal} from '../common';
import {TableHeader} from '../common/Table/TableHeader';
import {getInterviews} from '../../services/interviews/getInterviews';
import {ConversationTableRow} from './ConversationTableRow';
import {ConversationTableSkeleton} from './ConversationTableSkeleton';
import {InterviewListItem} from '../../types/interview';
import {deleteInterview} from '../../services/interviews';
import {CaretLeft, CaretRight} from '../../icons';

const ITEMS_PER_PAGE = 5;
const MAX_VISIBLE_PAGE_BUTTONS = 5;
const MAX_INTERVIEWS_TO_LOAD = 1000;

const getVisiblePageNumbers = (currentPage: number, totalPages: number) => {
  const visiblePageCount = Math.min(totalPages, MAX_VISIBLE_PAGE_BUTTONS);
  const halfWindow = Math.floor(visiblePageCount / 2);
  let firstPage = Math.max(1, currentPage - halfWindow);
  const lastPage = Math.min(totalPages, firstPage + visiblePageCount - 1);
  firstPage = Math.max(1, lastPage - visiblePageCount + 1);

  return Array.from(
    {length: lastPage - firstPage + 1},
    (_, index) => firstPage + index,
  );
};

export const ConversationTable = () => {
  const {t} = useTranslation();
  const [allInterviews, setAllInterviews] = useState<InterviewListItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [currentPage, setCurrentPage] = useState(1);
  const [interviewToDelete, setInterviewToDelete] = useState<number | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const COLUMN_HEADERS = [
    t('conversations.date'),
    t('conversations.clinicalCase'),
    t('conversations.duration'),
    t('conversations.status'),
    t('conversations.score'),
    t('conversations.action'),
  ] as const;

  const COLUMN_CLASS_NAMES = [
    'table-column-date',
    'table-column-case',
    'table-column-duration',
    'table-column-status',
    'table-column-score',
    'table-column-action',
  ] as const;

  const totalInterviews = allInterviews.length;
  const totalPages = Math.max(1, Math.ceil(totalInterviews / ITEMS_PER_PAGE));
  const pageStartIndex = (currentPage - 1) * ITEMS_PER_PAGE;
  const interviews = allInterviews.slice(pageStartIndex, pageStartIndex + ITEMS_PER_PAGE);
  const visiblePageNumbers = getVisiblePageNumbers(currentPage, totalPages);

  const confirmDelete = async () => {
    if (interviewToDelete === null || isDeleting) return;
    setIsDeleting(true);
    setDeleteError(null);
    try {
      await deleteInterview(interviewToDelete);
      setInterviewToDelete(null);
      const remainingInterviews = await fetchInterviews();
      const remainingPages = Math.max(1, Math.ceil(remainingInterviews.length / ITEMS_PER_PAGE));
      setCurrentPage((page) => Math.min(page, remainingPages));
    } catch (error) {
      console.error('Failed to delete interview:', error);
      setDeleteError(t('conversations.deleteFailed'));
    } finally {
      setIsDeleting(false);
    }
  };

  const fetchInterviews = async () => {
    try {
      setIsLoading(true);
      const fetchedInterviews = await getInterviews(MAX_INTERVIEWS_TO_LOAD, 0);
      setAllInterviews(fetchedInterviews);
      return fetchedInterviews;
    } catch (error) {
      console.error('Failed to fetch interviews:', error);
      // 401 errors are now handled globally by apiFetch
    } finally {
      setIsLoading(false);
    }
    return [];
  };

  useEffect(() => {
    void fetchInterviews();
  }, []);

  const renderTableControls = () => (
    <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm text-slate-600">
          {t('pagination.showing', {
            from: interviews.length > 0 ? pageStartIndex + 1 : 0,
            to: pageStartIndex + interviews.length,
            total: totalInterviews,
          })}
        </span>
      </div>

      <nav className="flex flex-wrap items-center gap-2" aria-label={t('conversations.myConversationHistory')}>
        <button
          type="button"
          onClick={() => setCurrentPage((previousPage) => Math.max(1, previousPage - 1))}
          disabled={currentPage === 1 || isLoading}
          className="flex h-9 w-9 items-center justify-center rounded-control border border-slate-300 bg-white text-slate-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40 [&_svg]:h-5 [&_svg]:w-5"
          aria-label={t('common.previous')}
          title={t('common.previous')}
        >
          <CaretLeft color="currentColor" />
        </button>
        {visiblePageNumbers.map((pageNumber) => (
          <button
            key={pageNumber}
            type="button"
            onClick={() => setCurrentPage(pageNumber)}
            className={`flex h-9 w-9 items-center justify-center rounded-control border text-sm font-semibold transition-colors ${
              pageNumber === currentPage
                ? 'border-brand-600 bg-brand-600 text-white'
                : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
            }`}
            aria-current={pageNumber === currentPage ? 'page' : undefined}
            aria-label={t('pagination.page', {page: pageNumber})}
          >
            {pageNumber}
          </button>
        ))}
        <button
          type="button"
          onClick={() => setCurrentPage((previousPage) => Math.min(totalPages, previousPage + 1))}
          disabled={currentPage >= totalPages || isLoading}
          className="flex h-9 w-9 items-center justify-center rounded-control border border-slate-300 bg-white text-slate-700 transition-colors hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40 [&_svg]:h-5 [&_svg]:w-5"
          aria-label={t('common.next')}
          title={t('common.next')}
        >
          <CaretRight color="currentColor" />
        </button>
      </nav>
    </div>
  );

  return (
    <section className="overflow-hidden rounded-card bg-white shadow-card">
      <header className="flex min-h-12 items-center border-b border-slate-200 px-4">
        <h2 className="component-title text-left">{t('conversations.myConversationHistory')}</h2>
      </header>
      {renderTableControls()}
      <div className="w-full px-4 pb-4 pt-0">
        <div className="w-full overflow-hidden bg-white max-md:overflow-x-auto">
          <table className="w-full table-fixed [&_thead_tr]:border-t-0">
            <TableHeader
              columns={COLUMN_HEADERS}
              columnClassNames={COLUMN_CLASS_NAMES}
              rowClassName="conversation-table-columns"
            />
            <tbody>
              {isLoading ? (
                <ConversationTableSkeleton />
              ) : interviews.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-6 py-8 text-center text-gray-500">
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
                    duration={interview.totalDuration}
                    clinicalCase={interview.clinicalCase}
                    score={interview.evaluationScore}
                    personality={interview.personality}
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
      </div>
      <Modal
        open={interviewToDelete !== null}
        closeAction={() => {
          if (!isDeleting) setInterviewToDelete(null);
        }}
        closeOnOutsideClick={!isDeleting}
        hasActions
        size="small"
      >
        <div className="dialog-shell">
          <header className="dialog-header">
            <h2 className="dialog-title">
              {t('conversations.deleteInterviewTitle')}
            </h2>
          </header>

          <div className="dialog-content">
            <p className="text-sm leading-6 text-slate-600">
              {t('conversations.deleteInterviewDescription')}
            </p>
            {deleteError && (
              <p role="alert" className="mt-3 text-sm text-danger-600">{deleteError}</p>
            )}
          </div>

          <footer className="dialog-footer">
            <div className="dialog-actions">
              <button
                type="button"
                disabled={isDeleting}
                onClick={() => setInterviewToDelete(null)}
                className="dialog-action dialog-action--secondary"
              >
                {t('common.cancel')}
              </button>
              <button
                type="button"
                disabled={isDeleting}
                onClick={() => void confirmDelete()}
                className="dialog-action dialog-action--danger"
              >
                {isDeleting ? t('conversations.deletingInterview') : t('common.delete')}
              </button>
            </div>
          </footer>
        </div>
      </Modal>
    </section>
  );
};

