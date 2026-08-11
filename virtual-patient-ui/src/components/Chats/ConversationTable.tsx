import {useEffect, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {FormInput} from '../common';
import {TableHeader} from '../common/Table/TableHeader';
import {getInterviews} from '../../services/interviews/getInterviews';
import {ConversationTableRow} from './ConversationTableRow';
import {InterviewListItem} from '../../types/interview';

const ITEMS_PER_PAGE = 10;

export const ConversationTable = () => {
  const {t} = useTranslation();
  const [interviews, setInterviews] = useState<InterviewListItem[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [currentPage, setCurrentPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  const COLUMN_HEADERS = [
    'ID',
    t('conversations.date'),
    t('conversations.clinicalCase'),
    t('conversations.personality'),
    t('conversations.duration'),
    t('conversations.status'),
    t('conversations.score'),
    t('conversations.feedback'),
  ] as const;

  const fetchInterviews = async (page: number) => {
    try {
      setIsLoading(true);
      const skip = (page - 1) * ITEMS_PER_PAGE;
      const fetchedInterviews = await getInterviews(ITEMS_PER_PAGE, skip);
      setInterviews(fetchedInterviews);
      setHasMore(fetchedInterviews.length === ITEMS_PER_PAGE);
    } catch (error) {
      console.error('Failed to fetch interviews:', error);
      // 401 errors are now handled globally by apiFetch
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchInterviews(currentPage);
  }, [currentPage]);

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="flex justify-between items-center p-6 border-b border-solid max-md:flex-col max-md:gap-4">
        <h2 className="text-xl font-semibold text-gray-900">{t('conversations.myConversationHistory')}</h2>
        <div className="flex gap-4 max-md:w-full">
          <FormInput
            label=""
            type="text"
            id="search"
            placeholder={t('conversations.searchCases')}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            margin={false}
          />
          <button className="flex gap-2 items-center px-5 py-3 text-base text-white bg-blue-600 rounded-lg cursor-pointer border-[none] max-md:w-auto">
            <span>{t('conversations.filter')}</span>
            <i className="ti ti-filter" />
          </button>
        </div>
      </div>
      <div className="w-full">
        <div className="overflow-hidden w-full bg-white rounded-lg max-md:overflow-x-auto">
          <table className="w-full">
            <TableHeader columns={COLUMN_HEADERS} />
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={8} className="px-6 py-8 text-center text-gray-500">
                    {t('common.loading')}
                  </td>
                </tr>
              ) : interviews.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-6 py-8 text-center text-gray-500">
                    {t('conversations.noConversations')}
                  </td>
                </tr>
              ) : (
                interviews.map((interview) => (
                  <ConversationTableRow
                    key={interview.id}
                    id={String(interview.id)}
                    createdAt={interview.createdAt}
                    startTime={interview.startTime}
                    status={interview.status}
                    duration={interview.totalDuration}
                    clinicalCase={interview.clinicalCase}
                    score={interview.evaluationScore?.toString()}
                    personality={interview.personality}
                  />
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
      <div className="flex justify-between items-center px-6 py-4 border-t border-solid">
        <div className="text-sm text-gray-700">
          {t('pagination.showing', {
            from: interviews.length > 0 ? (currentPage - 1) * ITEMS_PER_PAGE + 1 : 0,
            to: (currentPage - 1) * ITEMS_PER_PAGE + interviews.length,
          })}
        </div>
        <div className="flex gap-2 max-sm:flex-wrap max-sm:justify-center">
          <button
            onClick={() => setCurrentPage((prev) => Math.max(1, prev - 1))}
            disabled={currentPage === 1 || isLoading}
            className="flex items-center justify-center px-3.5 py-2 text-base text-gray-800 rounded-md border border-gray-300 border-solid cursor-pointer h-[34px] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {t('common.previous')}
          </button>
          <button className="flex items-center justify-center px-3.5 py-2 text-base text-white bg-blue-600 rounded-md border border-blue-600 border-solid h-[34px]">
            {currentPage}
          </button>
          <button
            onClick={() => setCurrentPage((prev) => prev + 1)}
            disabled={!hasMore || isLoading}
            className="flex items-center justify-center px-3.5 py-2 text-base text-gray-800 rounded-md border border-gray-300 border-solid cursor-pointer h-[34px] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {t('common.next')}
          </button>
        </div>
      </div>
    </div>
  );
};
