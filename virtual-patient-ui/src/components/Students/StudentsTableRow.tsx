import {DateTime} from '../common/DateTime';
import {FC} from 'react';
import {Badge} from '../common/Badge';
import {useNavigate} from 'react-router-dom';
import {useTranslation} from 'react-i18next';
import {OrganizationInterview} from '../../types/interview';
import {formatDuration} from '../../utils/duration';
import {interviewPath} from '../../utils/routes';
import {Button, EvaluationScore} from '../common';
import {ClinicalCaseCell} from '../common/ClinicalCaseCell';
import {Trash2} from 'lucide-react';

type Props = {
  interview: OrganizationInterview;
  canDelete: boolean;
  busy: boolean;
  onDelete: () => void;
};
export const StudentsTableRow: FC<Props> = ({
  interview,
  canDelete,
  busy,
  onDelete,
}) => {
  const navigate = useNavigate();
  const {t} = useTranslation();
  const statusVariant =
    interview.status === 'completed'
      ? 'success'
      : interview.status === 'interrupted'
        ? 'danger'
        : 'info';
  const canOpenInterview = !busy && interview.status === 'completed';
  const openInterview = () => {
    if (canOpenInterview) navigate(interviewPath(interview.id, 'review'));
  };
  return (
    <tr
      className={canOpenInterview ? 'ui-interactive-row' : undefined}
      tabIndex={canOpenInterview ? 0 : undefined}
      aria-label={canOpenInterview ? `${t('conversations.viewInterview')} ${interview.id}` : undefined}
      onClick={openInterview}
      onKeyDown={(event) => {
        if (event.target === event.currentTarget && (event.key === 'Enter' || event.key === ' ')) {
          event.preventDefault();
          openInterview();
        }
      }}
    >
      <td>
        <span>{interview.id}</span>
      </td>
      <td>
        <DateTime value={interview.createdAt} fallback={t('conversations.notAvailable')} />
      </td>
      <td>
        <div className="ui-text-pair">
          <span className="text-content default-text">{interview.userName}</span>
          <span className="text-content-muted secondary-text">
            {t(interview.ownerRole === 'teacher' ? 'auth.teacher' : 'auth.student')}
          </span>
        </div>
      </td>
      <td>
        <ClinicalCaseCell
          title={interview.clinicalCaseTitle}
          personality={interview.personality?.name}
        />
      </td>
      <td>
        {interview.totalDuration == null ? t('conversations.notAvailable') : formatDuration(interview.totalDuration)}
      </td>
      <td>
        <Badge tone={statusVariant}>
          {interview.status === 'processing' && interview.reviewProgress != null
            ? t('clinicalChat.processingProgress', {percentage: interview.reviewProgress})
            : t('clinicalChat.' + interview.status)}
        </Badge>
      </td>
      <td>
        {interview.status === 'processing' ? null : interview.evaluationScore != null ? (
          <EvaluationScore score={interview.evaluationScore} size="compact" />
        ) : (
          <span className="text-neutral-500 secondary-text">{t('conversations.notAvailable')}</span>
        )}
      </td>
      <td>
        <div className="ui-table-options ui-table-options--icons">
          <Button
            variant="secondary"
            disabled={busy || !canDelete}
            onClick={(event) => {
              event.stopPropagation();
              onDelete();
            }}
            className="ui-icon-button ui-button--hover-danger"
            aria-label={t('conversations.deleteInterview')}
            title={t('conversations.deleteInterview')}
          >
            <Trash2 aria-hidden="true" />
          </Button>
        </div>
      </td>
    </tr>
  );
};
