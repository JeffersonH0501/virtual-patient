import {FC, MouseEvent, useEffect, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {useNavigate} from 'react-router-dom';
import {ClinicalSession} from '../ClinicalSession';
import type {ClinicalCaseSimplified} from '../../services/clinicalCases';
import {EditIcon} from '../../icons';
import {useUser} from '../../hooks';
import {ROUTES} from '../../utils/routes';

type CaseCardProps = {
  type: 'Default' | 'Custom';
  clinicalCase: ClinicalCaseSimplified;
  caseIndex: number;
  expanded: boolean;
  onToggle: () => void;
};

export const CaseCard: FC<CaseCardProps> = ({
  type,
  clinicalCase,
  caseIndex,
  expanded,
  onToggle,
}) => {
  const {t} = useTranslation();
  const {user} = useUser();
  const navigate = useNavigate();
  const [hasOpened, setHasOpened] = useState(expanded);
  const displayNumber = caseIndex.toString().padStart(2, '0');
  const panelId = `case-configuration-${clinicalCase.id}`;
  const showEditAction =
    type === 'Custom' && (user?.role === 'teacher' || user?.role === 'superuser');

  useEffect(() => {
    if (expanded) {
      setHasOpened(true);
    }
  }, [expanded]);

  const handleEditClick = (event: MouseEvent<HTMLButtonElement>) => {
    event.stopPropagation();
    navigate(ROUTES.editCase.replace(':caseId', clinicalCase.id.toString()));
  };

  return (
    <article
      className={`w-full min-w-0 max-w-full rounded-lg border transition-colors duration-300 ${
        expanded ? 'overflow-visible' : 'overflow-hidden'
      } ${
        expanded ? 'border-blue-200 bg-white' : 'border-blue-200 bg-blue-50'
      }`}
    >
      <div className={`flex min-w-0 items-stretch overflow-hidden bg-blue-50 text-slate-800 transition-colors duration-200 hover:bg-blue-100/80 ${
        expanded ? 'rounded-t-[7px]' : 'rounded-[7px]'
      }`}>
        <div className="flex w-11 shrink-0 items-center justify-center border-r border-blue-200 bg-blue-100 px-1 text-sm font-bold text-blue-700 sm:w-14 sm:px-2">
          {displayNumber}
        </div>
        <p className="min-w-0 flex-1 break-words px-3 py-3 text-sm font-medium leading-5 sm:px-4">
          {clinicalCase.description}
        </p>
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={expanded}
          aria-controls={panelId}
          aria-label={
            expanded
              ? t('clinicalCases.hideConfiguration')
              : t('clinicalCases.configureCase')
          }
          className="flex w-11 shrink-0 items-center justify-center !rounded-none border-0 border-l border-blue-500 bg-blue-600 p-0 text-white transition-colors hover:border-l-blue-500 hover:bg-blue-700 focus:!outline-none focus-visible:!outline-none focus-visible:shadow-[inset_0_0_0_3px_#facc15] sm:w-14"
        >
          <svg
            aria-hidden="true"
            viewBox="0 0 20 20"
            fill="none"
            className={`h-5 w-5 transition-transform duration-300 ${expanded ? 'rotate-180' : ''}`}
          >
            <path
              d="m5 7.5 5 5 5-5"
              stroke="currentColor"
              strokeWidth="1.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      </div>

      <div
        id={panelId}
        aria-hidden={!expanded}
        inert={!expanded}
        className={`grid min-w-0 transition-[grid-template-rows,opacity] duration-300 ease-out ${
          expanded ? 'grid-rows-[1fr] opacity-100' : 'grid-rows-[0fr] opacity-0'
        }`}
      >
        <div className={`min-h-0 min-w-0 ${expanded ? 'overflow-visible' : 'overflow-hidden'}`}>
          {hasOpened && (
            <div className="min-w-0 max-w-full rounded-b-[7px] border-t border-blue-200 bg-white">
              {showEditAction && (
                <div className="flex justify-end px-4 pt-4 sm:px-5">
                  <button
                    type="button"
                    onClick={handleEditClick}
                    className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 transition hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-300"
                  >
                    <EditIcon size={15} />
                    {t('clinicalCases.editCase')}
                  </button>
                </div>
              )}
              <ClinicalSession clinicalCase={clinicalCase} onCancel={onToggle} />
            </div>
          )}
        </div>
      </div>
    </article>
  );
};
