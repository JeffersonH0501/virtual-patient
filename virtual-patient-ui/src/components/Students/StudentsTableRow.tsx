import {FC, useMemo} from 'react';
import {Badge} from '../common/Table/Badge';
import {useNavigate} from 'react-router-dom';
import {useTranslation} from 'react-i18next';
import {OrganizationInterview} from '../../types/interview';
import {formatDuration} from '../../utils/duration';
import {useUser} from '../../hooks/useUser';
import {interviewPath} from '../../utils/routes';
import {EvaluationScore} from '../common';

type StudentsTableRowProps = {
  interview: OrganizationInterview;
};

export const StudentsTableRow: FC<StudentsTableRowProps> = ({
  interview,
}) => {
  const navigate = useNavigate();
  const {t} = useTranslation();
  const {user} = useUser();

  // Check if any teacher feedback is from the current user
  const reviewedByYou = useMemo(() => {
    if (!user || !interview.teacherFeedback) return false;
    return interview.teacherFeedback.some((feedback) => feedback.reviewedByYou);
  }, [user, interview.teacherFeedback]);

  // Calculate live duration for in-progress interviews
  const liveDuration = useMemo(() => {
    if (interview.status === 'in_progress' && interview.startTime) {
      const now = new Date().getTime();
      const start = new Date(interview.startTime).getTime();
      return Math.floor((now - start) / 1000);
    }
    return 0;
  }, [interview.status, interview.startTime]);

  const handleRowClick = () => {
    const isTerminal = interview.status === 'completed' || interview.status === 'interrupted';
    navigate(interviewPath(interview.id, isTerminal ? 'review' : 'session'));
  };

  return (
    <tr
      className="flex px-0 py-4 border-b border-gray-100 border-solid max-md:min-w-table cursor-pointer hover:bg-gray-50"
      onClick={handleRowClick}
    >
      {/* ID Column */}
      <td className="table-column-compact px-6 py-0 text-left text-sm text-gray-500 max-sm:px-3 max-sm:py-0">
        <span className="font-mono text-xs text-gray-600">
          #{interview.id}
        </span>
      </td>

      {/* Student Column */}
      <td className="table-column-expanded px-6 py-0 text-left text-sm text-gray-500 max-sm:px-3 max-sm:py-0">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-blue-100 rounded-full flex items-center justify-center">
            <span className="text-xs font-medium text-blue-600">
              {(interview.userName || '').charAt(0).toUpperCase()}
            </span>
          </div>
          <span className="font-medium text-gray-900">
            {interview.userName}
          </span>
        </div>
      </td>

      {/* Case Type Column */}
      <td className="flex flex-1 items-center px-6 py-0 text-left text-sm text-gray-500 max-sm:px-3 max-sm:py-0">
        <Badge variant="green" className="max-w-status-badge truncate block">
          {interview.clinicalCaseTitle}
        </Badge>
      </td>

      {/* Personality Column */}
      <td className="flex flex-1 items-center px-6 py-0 text-left text-sm text-gray-500 max-sm:px-3 max-sm:py-0">
        <span className="text-gray-900">
          {interview.personality?.name || 'N/A'}
        </span>
      </td>

      {/* Duration Column */}
      <td className="flex-1 px-6 py-0 text-left text-sm text-gray-500 max-sm:px-3 max-sm:py-0">
        {interview.status === 'in_progress' && interview.startTime ? formatDuration(liveDuration, t('conversations.min')) : formatDuration(interview.totalDuration, t('conversations.min'))}
      </td>

      {/* Score Column */}
      <td className="flex-1 px-6 py-0 text-left text-sm text-gray-500 max-sm:px-3 max-sm:py-0">
        {interview.evaluationScore != null ? (
          <EvaluationScore score={interview.evaluationScore} size="small" />
        ) : 'N/A'}
      </td>

      {/* Status Column */}
      <td className="flex flex-1 items-center px-6 py-0 text-left text-sm text-gray-500 max-sm:px-3 max-sm:py-0">
        <Badge
          variant={
            interview.status === 'completed'
              ? 'orange'
              : interview.status === 'interrupted'
                ? 'red'
                : 'green'
          }
        >
          {t(`clinicalChat.${interview.status}`)}
        </Badge>
      </td>

      {/* Reviewed by You Column */}
      <td className="flex flex-1 items-center px-6 py-0 text-left text-sm text-gray-500 max-sm:px-3 max-sm:py-0">
        <Badge variant={reviewedByYou ? 'green' : 'purple'}>
          {reviewedByYou ? t('common.yes') : t('common.no')}
        </Badge>
      </td>

    </tr>
  );
};
