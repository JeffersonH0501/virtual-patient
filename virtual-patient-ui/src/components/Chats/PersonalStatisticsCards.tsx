import {FC, useEffect, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {StatCard} from './StatCard';
import {PersonalStatisticsCardsSkeleton} from './PersonalStatisticsCardsSkeleton';
import {getPersonalStatistics, PersonalStatistics} from '../../services/statistics/getPersonalStatistics';
import {EvaluationScore} from '../common';

export const PersonalStatisticsCards: FC = () => {
  const {t} = useTranslation();
  const [statistics, setStatistics] = useState<PersonalStatistics | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchStatistics = async () => {
      try {
        setIsLoading(true);
        setError(null);
        const personalStats = await getPersonalStatistics();
        setStatistics(personalStats);
      } catch (err) {
        console.error('Failed to fetch personal statistics:', err);
        setError(err instanceof Error ? err.message : 'Failed to fetch statistics');
      } finally {
        setIsLoading(false);
      }
    };

    fetchStatistics();
  }, []);

  const formatDuration = (seconds: number): string => {
    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const remainingSeconds = Math.floor(seconds % 60);

    // If we have days, only show days
    if (days > 0) {
      return `${days}d`;
    }

    // If we have hours, show hours (round up if there are minutes or seconds)
    if (hours > 0) {
      const hasMinutesOrSeconds = minutes > 0 || remainingSeconds > 0;
      return hasMinutesOrSeconds ? `${hours + 1}h` : `${hours}h`;
    }

    // If we only have minutes, show minutes (round up if there are seconds)
    if (minutes > 0) {
      const hasSeconds = remainingSeconds > 0;
      return hasSeconds ? `${minutes + 1}m` : `${minutes}m`;
    }

    // If we only have seconds, show seconds
    return `${remainingSeconds}s`;
  };

  if (isLoading) {
    return <PersonalStatisticsCardsSkeleton />;
  }

  if (error) {
    return (
      <div className="grid gap-2 md:grid-cols-3">
        <StatCard title={t('conversations.completedCases')} value="N/A" change={error} isNegative />
        <StatCard title={t('conversations.averageDuration')} value="N/A" change={error} isNegative />
        <StatCard title={t('conversations.overallScore')} value="N/A" change={error} isNegative />
      </div>
    );
  }

  if (!statistics) {
    return null;
  }

  return (
    <div className="grid gap-2 md:grid-cols-3">
      <StatCard
        title={t('conversations.completedCases')}
        value={statistics.completedCases.toString()}
      />
      <StatCard
        title={t('conversations.averageDuration')}
        value={statistics.hasDurationData ? formatDuration(statistics.averageDurationSeconds) : 'N/A'}
      />
      <StatCard
        title={t('conversations.overallScore')}
        value={statistics.hasScoreData ? <EvaluationScore score={statistics.averageScore} size="large" /> : 'N/A'}
      />
    </div>
  );
};
