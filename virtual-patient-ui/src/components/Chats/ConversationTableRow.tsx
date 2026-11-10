import {DateTime} from '../common/DateTime';
import {ClinicalCaseCell} from '../common/ClinicalCaseCell';
import {FC} from 'react';
import {Badge} from '../common/Badge';
import {useNavigate} from 'react-router-dom';
import {ClinicalCaseSimplified} from '../../services/clinicalCases';
import {useTranslation} from 'react-i18next';
import {formatDuration} from '../../utils/duration';
import {Personality} from '../../types/personality';
import {interviewPath, ROUTES} from '../../utils/routes';
import {Button, EvaluationScore} from '../common';
import {Trash2} from 'lucide-react';

type TableRowProps = {
  id: string;
  status: string;
  duration: number | null;
  createdAt: string;
  startTime: string | null;
  score?: number | null;
  clinicalCase: ClinicalCaseSimplified;
  personality?: Personality | null;
  isAssigned?: boolean;
  manualRatingStatus?: 'pending' | 'in_progress' | 'submitted';
  onDelete: (id: number) => void;
  canRetryCompletion?: boolean;
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
  isAssigned = false,
  manualRatingStatus = 'pending',
  onDelete,
  canRetryCompletion = false,
}) => {
  const navigate = useNavigate();
  const {t} = useTranslation();

  const canOpenInterview = status === 'completed' || status === 'in_progress' || status === 'processing' || (status === 'interrupted' && canRetryCompletion);
  const handleOpenInterview = () => {
    if (!canOpenInterview) return;
    if (status === 'completed' || status === 'processing' || (status === 'interrupted' && canRetryCompletion)) {
      navigate(interviewPath(id, 'review'));
      return;
    }
    if (status === 'in_progress' && startTime) {
      navigate(interviewPath(id, 'session'));
    } else if (status === 'in_progress') {
      navigate(ROUTES.calibration, {state: {draftInterviewId: Number(id)}});
    }
  };

  const awaitingManualRating = (status === 'completed' || status === 'processing') && manualRatingStatus !== 'submitted';
  const statusVariant = status === 'completed' && !awaitingManualRating ? 'success' : status === 'interrupted' ? 'danger' : 'info';

  return (
    <tr className={canOpenInterview ? 'ui-interactive-row' : undefined}
      tabIndex={canOpenInterview ? 0 : undefined}
      aria-label={canOpenInterview ? `${t('conversations.viewInterview')} ${id}` : undefined}
      onClick={handleOpenInterview}
      onKeyDown={(event) => {
        if (event.target === event.currentTarget && (event.key === 'Enter' || event.key === ' ')) {
          event.preventDefault();
          handleOpenInterview();
        }
      }}>
      <td>{id}</td>
      <td>
        <DateTime value={createdAt} />
      </td>
      <td>
        <ClinicalCaseCell title={clinicalCase.title} personality={personality?.name} />
      </td>
      <td>
        {status === 'in_progress' && !startTime
          ? t('calibration.notStarted')
          : duration == null ? t('conversations.notAvailable') : formatDuration(duration)}
      </td>
      <td>
        <div className="flex flex-wrap gap-layout">
        {isAssigned && <Badge tone="info">{t('conversations.assigned')}</Badge>}
        <Badge tone={statusVariant}>
          {status === 'in_progress' && !startTime
            ? t('calibration.pending')
            : awaitingManualRating
              ? t('conversations.pendingEvaluation')
              : status === 'processing' ? t('conversations.evaluating')
              : t(`clinicalChat.${status}`)}
        </Badge>
        </div>
      </td>
      <td>
        {status === 'processing' ? null : score != null ? (
          <EvaluationScore score={score} size="compact" />
        ) : (
          <span className="text-neutral-500 secondary-text">{t('conversations.notAvailable')}</span>
        )}
      </td>
      <td>
        <div className="ui-table-options ui-table-options--icons">
          {!isAssigned && <Button
            variant="secondary"
            onClick={(event) => {
              event.stopPropagation();
              onDelete(Number(id));
            }}
            className="ui-icon-button ui-button--hover-danger"
            aria-label={t('conversations.deleteInterview')}
            title={t('conversations.deleteInterview')}
          >
            <Trash2 aria-hidden="true" />
          </Button>}
        </div>
      </td>
    </tr>
  );
};
