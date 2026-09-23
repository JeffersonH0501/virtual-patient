import {FC, useMemo} from 'react';
import {Badge} from '../common/Table/Badge';
import {useNavigate} from 'react-router-dom';
import {ClinicalCaseSimplified} from '../../services/clinicalCases';
import {useTranslation} from 'react-i18next';
import {formatDuration} from '../../utils/duration';
import {Personality} from '../../types/personality';
import {interviewPath} from '../../utils/routes';
import {Eye, Trash} from '../../icons';
import {EvaluationScore} from '../common';

type TableRowProps = {
  id: string;
  status: string;
  duration: number | null;
  createdAt: string;
  startTime: string | null;
  score?: number | null;
  clinicalCase: ClinicalCaseSimplified;
  personality?: Personality | null;
  analysisProgress?: {completed: number; total: number; percentage: number} | null;
  onDelete: (id: number) => void;
};

export const ConversationTableRow: FC<TableRowProps> = ({
  id,
  createdAt,
  status,
  duration,
  startTime,
  score,
  clinicalCase,
  personality,
  analysisProgress,
  onDelete,
}) => {
  const navigate = useNavigate();
  const {t} = useTranslation();

  // Calculate live duration for in-progress interviews
  const liveDuration = useMemo(() => {
    if (status === 'in_progress' && startTime) {
      const now = new Date().getTime();
      const start = new Date(startTime).getTime();
      return Math.floor((now - start) / 1000);
    }
    return 0;
  }, [status, startTime]);

  const canOpenInterview = status === 'completed' || status === 'in_progress';
  const handleOpenInterview = () => {
    if (status === 'completed') {
      navigate(interviewPath(id, 'review'));
      return;
    }
    if (status === 'in_progress') {
      navigate(interviewPath(id, startTime ? 'session' : 'calibration'));
    }
  };

  const statusVariant =
    status === 'completed' ? 'green' : status === 'interrupted' ? 'red' : 'blue';

  return (
    <tr
      className="conversation-table-columns px-0 py-4 border-b border-gray-100 border-solid max-md:min-w-table hover:bg-gray-50"
    >
      <td className="flex min-w-0 table-column-date flex-col justify-center gap-0.5 px-6 py-0 text-left text-sm leading-5 text-gray-500 max-sm:px-3 max-sm:py-0">
        <span>{new Date(createdAt).toLocaleDateString(undefined, {
          year: 'numeric',
          month: 'short',
          day: 'numeric',
        })}</span>
        <span>{new Date(createdAt).toLocaleTimeString(undefined, {
          hour: '2-digit',
          minute: '2-digit',
        })}</span>
      </td>
      <td className="flex min-w-0 table-column-case flex-col justify-center gap-0.5 px-6 py-0 text-left text-sm leading-5 max-sm:px-3 max-sm:py-0">
        <span className="font-medium text-gray-900">{clinicalCase.title}</span>
        <span className="text-xs text-gray-500">{personality?.name || 'N/A'}</span>
      </td>
      <td className="flex min-w-0 table-column-duration items-center px-6 py-0 text-left text-sm text-gray-500 max-sm:px-3 max-sm:py-0">
        {status === 'in_progress' && !startTime
          ? t('calibration.notStarted')
          : status === 'in_progress'
            ? formatDuration(liveDuration, t('conversations.min'))
            : formatDuration(duration, t('conversations.min'))}
      </td>
      <td className="flex min-w-0 table-column-status flex-wrap items-center gap-2 px-6 py-0 text-left text-sm text-gray-500 max-sm:px-3 max-sm:py-0">
        <Badge variant={statusVariant}>{status === 'in_progress' && !startTime ? t('calibration.pending') : t(`clinicalChat.${status}`)}</Badge>
        {(status === 'in_progress' || status === 'processing') && analysisProgress && analysisProgress.total > 0 && (
          <span className="text-xs font-medium text-brand-700">
            {t('conversations.analysisProgress', analysisProgress)}
          </span>
        )}
      </td>
      <td className="flex min-w-0 table-column-score items-center px-6 py-0 text-left text-sm text-gray-500 max-sm:px-3 max-sm:py-0">
        {score != null ? (
          <EvaluationScore score={score} size="small" />
        ) : (
          <span className="text-xs text-slate-500">{t('conversations.notAvailable')}</span>
        )}
      </td>
      <td className="flex min-w-0 table-column-action items-center justify-start gap-2 px-6 py-0 max-sm:px-3">
        <button
          type="button"
          onClick={handleOpenInterview}
          disabled={!canOpenInterview}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-control border-0 bg-slate-100 text-slate-700 transition-colors hover:bg-blue-50 hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-slate-100 disabled:hover:text-slate-700 [&_svg]:h-5 [&_svg]:w-5"
          aria-label={t('conversations.viewInterview')}
          title={t('conversations.viewInterview')}
        >
          <Eye />
        </button>
        <button
          type="button"
          onClick={() => onDelete(Number(id))}
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-control border-0 bg-slate-100 text-slate-700 transition-colors hover:bg-danger-50 hover:text-danger-700 [&_svg]:h-5 [&_svg]:w-5"
          aria-label={t('conversations.deleteInterview')}
          title={t('conversations.deleteInterview')}
        >
          <Trash />
        </button>
      </td>
    </tr>
  );
};
