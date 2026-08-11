import {FC, useEffect, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {StatCard} from './StatCard';
import {CheckIcon, ClockIcon, StarIcon} from '../../icons';
import {getPersonalStatistics, PersonalStatistics} from '../../services/statistics/getPersonalStatistics';

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

  const formatScore = (score: number): string => {
    return `${score.toFixed(1)}/10`;
  };

  if (isLoading) {
    return (
      <div className="flex gap-16 mb-16 max-md:flex-col max-md:gap-6">
        <StatCard title={t('conversations.completedCases')} value={t('common.loading')} icon={<CheckIcon />} />
        <StatCard title={t('conversations.averageDuration')} value={t('common.loading')} icon={<ClockIcon />} />
        <StatCard title={t('conversations.overallScore')} value={t('common.loading')} icon={<StarIcon />} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex gap-16 mb-16 max-md:flex-col max-md:gap-6">
        <StatCard title={t('conversations.completedCases')} value="N/A" icon={<CheckIcon />} change={error} isNegative />
        <StatCard title={t('conversations.averageDuration')} value="N/A" icon={<ClockIcon />} change={error} isNegative />
        <StatCard title={t('conversations.overallScore')} value="N/A" icon={<StarIcon />} change={error} isNegative />
      </div>
    );
  }

  if (!statistics) {
    return null;
  }

  return (
    <div className="flex gap-16 mb-16 max-md:flex-col max-md:gap-6">
      <StatCard
        title={t('conversations.completedCases')}
        value={statistics.completedCases.toString()}
        icon={<CheckIcon />}
        change={t('conversations.totalCompleted')}
      />
      <StatCard
        title={t('conversations.averageDuration')}
        value={statistics.hasDurationData ? formatDuration(statistics.averageDurationSeconds) : 'N/A'}
        icon={<ClockIcon />}
        change={statistics.hasDurationData ? `${statistics.totalCompletedCases} ${t('conversations.cases')}` : t('conversations.noData')}
      />
      <StatCard
        title={t('conversations.overallScore')}
        value={statistics.hasScoreData ? formatScore(statistics.averageScore) : 'N/A'}
        icon={<StarIcon />}
        change={statistics.hasScoreData ? `${statistics.totalEvaluations} ${t('conversations.evaluations')}` : t('conversations.noData')}
      />
    </div>
  );
};
