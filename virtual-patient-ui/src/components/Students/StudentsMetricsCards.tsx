import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { StatCard } from '../Chats/StatCard';
import { getStudentsMetrics, StudentsMetrics } from '../../services/students/getStudentsMetrics';
import { CheckIcon, ClockIcon, StarIcon } from '../../icons';

export const StudentsMetricsCards = () => {
  const { t } = useTranslation();
  const [metrics, setMetrics] = useState<StudentsMetrics | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchMetrics = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const studentsMetrics = await getStudentsMetrics('1');
        setMetrics(studentsMetrics);
      } catch (err) {
        console.error('Failed to fetch students metrics:', err);
        setError(err instanceof Error ? err.message : 'Failed to fetch metrics');
      } finally {
        setIsLoading(false);
      }
    };

    fetchMetrics();
  }, []);

  if (isLoading) {
    return (
      <div className="flex gap-16 mb-16 max-md:flex-col max-md:gap-6">
        <div className="flex-1 p-6 bg-white rounded-lg shadow animate-pulse">
          <div className="h-4 bg-gray-200 rounded mb-4"></div>
          <div className="h-8 bg-gray-200 rounded mb-2"></div>
          <div className="h-4 bg-gray-200 rounded"></div>
        </div>
        <div className="flex-1 p-6 bg-white rounded-lg shadow animate-pulse">
          <div className="h-4 bg-gray-200 rounded mb-4"></div>
          <div className="h-8 bg-gray-200 rounded mb-2"></div>
          <div className="h-4 bg-gray-200 rounded"></div>
        </div>
        <div className="flex-1 p-6 bg-white rounded-lg shadow animate-pulse">
          <div className="h-4 bg-gray-200 rounded mb-4"></div>
          <div className="h-8 bg-gray-200 rounded mb-2"></div>
          <div className="h-4 bg-gray-200 rounded"></div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex gap-16 mb-16 max-md:flex-col max-md:gap-6">
        <div className="flex-1 p-6 bg-white rounded-lg shadow">
          <div className="text-center text-red-500">{error}</div>
        </div>
        <div className="flex-1 p-6 bg-white rounded-lg shadow">
          <div className="text-center text-red-500">{error}</div>
        </div>
        <div className="flex-1 p-6 bg-white rounded-lg shadow">
          <div className="text-center text-red-500">{error}</div>
        </div>
      </div>
    );
  }

  if (!metrics) {
    return null;
  }

  return (
    <div className="flex gap-16 mb-16 max-md:flex-col max-md:gap-6">
      <StatCard
        title={t('students.activeStudents')}
        value={metrics.activeStudentsCount.toString()}
        icon={<ClockIcon />}
        change={t('students.currentlyActive')}
      />
      <StatCard
        title={t('students.completedStudents')}
        value={metrics.completedStudentsCount.toString()}
        icon={<CheckIcon />}
        change={t('students.finishedCases')}
      />
      <StatCard
        title={t('students.averageScore')}
        value={metrics.hasData ? `${metrics.averageScore.toFixed(1)}/10` : 'N/A'}
        icon={<StarIcon />}
        change={metrics.hasData ? `${metrics.totalEvaluations} ${t('students.evaluations')}` : t('students.noData')}
      />
    </div>
  );
};
