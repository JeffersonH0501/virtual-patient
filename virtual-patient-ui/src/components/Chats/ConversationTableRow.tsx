import {FC, useMemo} from 'react';
import {Badge} from '../common/Table/Badge';
import {useNavigate} from 'react-router-dom';
import {ClinicalCaseSimplified} from '../../services/clinicalCases';
import {useTranslation} from 'react-i18next';
import {formatDuration} from '../../utils/duration';
import {Personality} from '../../types/personality';

type TableRowProps = {
  id: string;
  status: string;
  duration: number | null;
  createdAt: string;
  startTime: string;
  score?: string;
  feedback?: {
    label: string;
    variant: 'blue' | 'green';
  };
  clinicalCase: ClinicalCaseSimplified;
  personality?: Personality | null;
  onDelete: (id: number) => void;
};

export const ConversationTableRow: FC<TableRowProps> = ({
  id,
  createdAt,
  status,
  duration,
  startTime,
  score,
  feedback,
  clinicalCase,
  personality,
  onDelete,
}) => {
  const navigate = useNavigate();
  const {t} = useTranslation();

  // Calculate live duration for active interviews
  const liveDuration = useMemo(() => {
    if (status === 'active') {
      const now = new Date().getTime();
      const start = new Date(startTime).getTime();
      return Math.floor((now - start) / 1000);
    }
    return 0;
  }, [status, startTime]);

  const handleRowClick = () => {
    navigate(`/clinical-chat/${id}`);
  };

  return (
    <tr
      className="flex px-0 py-4 border-b border-gray-100 border-solid max-md:min-w-[900px] cursor-pointer hover:bg-gray-50"
      onClick={handleRowClick}
    >
      {/* ID Column */}
      <td className="flex-[0.5] px-6 py-0 text-left text-sm text-gray-500 max-sm:px-3 max-sm:py-0">
        <span className="font-mono text-xs text-gray-600">
          #{id}
        </span>
      </td>

      <td className="flex-[1.5] px-6 py-0 text-left text-sm text-gray-500 max-sm:px-3 max-sm:py-0">
        {new Date(createdAt).toLocaleString(undefined, {
          year: 'numeric',
          month: 'short',
          day: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        })}
      </td>
      <td className="flex flex-1 items-center px-6 py-0 text-left text-sm text-gray-500 max-sm:px-3 max-sm:py-0">
        <Badge variant="green" className="max-w-[120px] truncate block">
          {clinicalCase.title}
        </Badge>
      </td>
      <td className="flex flex-1 items-center px-6 py-0 text-left text-sm text-gray-500 max-sm:px-3 max-sm:py-0">
        <span className="text-gray-900">
          {personality?.name || 'N/A'}
        </span>
      </td>
      <td className="flex-1 px-6 py-0 text-left text-sm text-gray-500 max-sm:px-3 max-sm:py-0">
        {status === 'active' ? formatDuration(liveDuration, t('conversations.min')) : formatDuration(duration, t('conversations.min'))}
      </td>
      <td className="flex flex-1 items-center px-6 py-0 text-left text-sm text-gray-500 max-sm:px-3 max-sm:py-0">
        <Badge variant={status === 'completed' ? 'orange' : 'green'}>{t(`clinicalChat.${status}`)}</Badge>
      </td>
      <td className="flex-1 px-6 py-0 text-left text-sm text-gray-500 max-sm:px-3 max-sm:py-0">
        {score}
      </td>
      <td className="flex flex-1 items-center px-6 py-0 text-left text-sm text-gray-500 max-sm:px-3 max-sm:py-0">
        <Badge variant="blue">{feedback?.label || t('common.noFeedback')}</Badge>
      </td>
      <td className="flex flex-[0.6] items-center justify-center px-3 py-0">
        <button
          type="button"
          onClick={(event) => {
            event.stopPropagation();
            onDelete(Number(id));
          }}
          className="flex h-9 w-9 items-center justify-center rounded-lg bg-rose-50 text-rose-600 transition-colors hover:bg-rose-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose-600"
          aria-label={t('conversations.deleteInterview')}
          title={t('conversations.deleteInterview')}
        >
          <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M4 7h16M9 7V4h6v3m-8 0 1 13h8l1-13M10 11v5m4-5v5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </td>
    </tr>
  );
};
