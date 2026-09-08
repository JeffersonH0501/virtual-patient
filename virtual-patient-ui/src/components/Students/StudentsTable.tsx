import {useEffect, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {FormInput} from '../common';
import {TableHeader} from '../common/Table/TableHeader';
import {getOrganizationInterviews} from '../../services/interviews/getOrganizationInterviews';
import {StudentsTableRow} from './StudentsTableRow';
import {OrganizationInterview} from '../../types/interview';
import {Funnel} from '../../icons';

const ITEMS_PER_PAGE = 10;

export const StudentsTable = () => {
  const {t} = useTranslation();
  const [interviews, setInterviews] = useState<OrganizationInterview[]>([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  const COLUMN_HEADERS = [
    'ID',
    t('students.student'),
    t('students.caseType'),
    t('students.personality'),
    t('students.duration'),
    t('students.score'),
    t('students.status'),
    t('students.reviewByYou'),
  ] as const;

  const fetchOrganizationInterviews = async (page: number) => {
    try {
      setIsLoading(true);
      setError(null);
      const skip = (page - 1) * ITEMS_PER_PAGE;
      const organizationInterviews = await getOrganizationInterviews('1', skip, ITEMS_PER_PAGE);
      setInterviews(organizationInterviews);
      setHasMore(organizationInterviews.length === ITEMS_PER_PAGE);
    } catch (err) {
      console.error('Failed to fetch organization interviews:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch interviews');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchOrganizationInterviews(currentPage);
  }, [currentPage]);


  // Filter interviews based on search term
  const filteredInterviews = interviews.filter((interview) =>
    interview.clinicalCaseTitle.toLowerCase().includes(searchTerm.toLowerCase()) ||
    [interview.userFirstName, interview.userLastName].filter(Boolean).join(' ').toLowerCase().includes(searchTerm.toLowerCase()),
  );

  if (isLoading) {
    return (
      <div className="bg-white rounded-lg shadow">
        <div className="flex justify-center items-center p-8">
          <div className="text-lg text-gray-600">{t('common.loading')}</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow">
        <div className="flex justify-center items-center p-8">
          <div className="text-lg text-red-600">{error}</div>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow">
      <div className="flex justify-between items-center p-6 border-b border-solid max-md:flex-col max-md:gap-4">
        <h2 className="text-xl font-semibold text-gray-900">{t('students.recentStudentConversations')}</h2>
        <div className="flex gap-4 max-md:w-full">
          <FormInput
            label=""
            type="text"
            id="search"
            placeholder={t('students.searchStudents')}
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            margin={false}
          />
          <button className="flex gap-2 items-center px-5 py-3 text-base text-white bg-blue-600 rounded-lg cursor-pointer border-none max-md:w-auto">
            <span>{t('conversations.filter')}</span>
            <span className="block h-4 w-4 [&_svg]:h-full [&_svg]:w-full"><Funnel color="currentColor" /></span>
          </button>
        </div>
      </div>
      <div className="w-full">
        <div className="overflow-hidden w-full bg-white rounded-lg max-md:overflow-x-auto">
          <table className="w-full">
            <TableHeader columns={COLUMN_HEADERS} />
            <tbody>
              {filteredInterviews.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-6 py-8 text-center text-gray-500">
                    {searchTerm ? t('students.noResults') : t('students.noInterviews')}
                  </td>
                </tr>
              ) : (
                filteredInterviews.map((interview) => (
                  <StudentsTableRow
                    key={interview.id}
                    interview={interview}
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
            className="flex items-center justify-center px-3.5 py-2 text-base text-gray-800 rounded-md border border-gray-300 border-solid cursor-pointer h-pagination-control disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {t('common.previous')}
          </button>
          <button className="flex items-center justify-center px-3.5 py-2 text-base text-white bg-blue-600 rounded-md border border-blue-600 border-solid h-pagination-control">
            {currentPage}
          </button>
          <button
            onClick={() => setCurrentPage((prev) => prev + 1)}
            disabled={!hasMore || isLoading}
            className="flex items-center justify-center px-3.5 py-2 text-base text-gray-800 rounded-md border border-gray-300 border-solid cursor-pointer h-pagination-control disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {t('common.next')}
          </button>
        </div>
      </div>
    </div>
  );
};
