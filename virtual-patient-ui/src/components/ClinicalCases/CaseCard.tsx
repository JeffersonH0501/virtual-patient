import {FC, useEffect, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {ClinicalSession} from '../ClinicalSession';
import type {ClinicalCaseSimplified} from '../../services/clinicalCases';
import {ChevronDown} from 'lucide-react';
import {useUser} from '../../hooks';
import {CaseDetailsDialog} from './CaseDetailsDialog';
import {MotionHeight} from '../common/Motion';
import {useEntrance} from '../common/Motion/hooks';

type CaseCardProps = {
  clinicalCase: ClinicalCaseSimplified;
  caseIndex: number;
  expanded: boolean;
  onToggle: () => void;
};

export const CaseCard: FC<CaseCardProps> = ({clinicalCase, caseIndex, expanded, onToggle}) => {
  const {t} = useTranslation();
  const {user} = useUser();
  const entrance = useEntrance<HTMLElement>(caseIndex - 1, true);
  const [hasOpened, setHasOpened] = useState(expanded);
  const displayNumber = caseIndex.toString().padStart(2, '0');
  const panelId = `case-configuration-${clinicalCase.id}`;
  const isSuperuser = user?.role === 'superuser';
  const [detailsOpen, setDetailsOpen] = useState(false);

  useEffect(() => {
    if (expanded) {
      setHasOpened(true);
    }
  }, [expanded]);

  return (
    <article
      ref={entrance}
      className={`w-full min-w-0 max-w-full rounded-lg border motion-colors ${
        expanded ? 'overflow-visible' : 'overflow-hidden'
      } ${expanded ? 'border-brand-200 bg-white' : 'border-brand-200 bg-brand-50'}`}
    >
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
        aria-describedby={`case-description-${clinicalCase.id}`}
        className={`case-disclosure-row flex w-full min-w-0 items-stretch overflow-hidden bg-brand-50 text-neutral-800 motion-colors hover:bg-brand-100/80 ${
          expanded ? 'rounded-t-case' : 'rounded-case'
        }`}
      >
        <span className="flex w-11 shrink-0 items-center justify-center ui-divider-right border-brand-200 bg-brand-100 px-inset text-brand-700 sm:w-14 sm:px-inset default-title">
          {displayNumber}
        </span>
        <span
          id={`case-description-${clinicalCase.id}`}
          className="min-w-0 flex-1 break-words px-inset py-inset sm:px-inset medium-text"
        >
          {clinicalCase.description}
        </span>
        <span className="case-disclosure" aria-hidden="true">
          <span
            className={`block h-5 w-5 motion-chevron [&_svg]:h-full [&_svg]:w-full ${expanded ? 'rotate-180' : ''}`}
          >
            <ChevronDown />
          </span>
        </span>
      </button>

      <MotionHeight id={panelId} expanded={expanded} className="min-w-0">
        <div className={`min-h-0 min-w-0 ${expanded ? 'overflow-visible' : 'overflow-hidden'}`}>
          {hasOpened && (
            <div className="min-w-0 max-w-full rounded-b-case border-t border-brand-200 bg-white">
              <ClinicalSession clinicalCase={clinicalCase} onCancel={onToggle}
                onView={isSuperuser ? () => setDetailsOpen(true) : undefined} />
            </div>
          )}
        </div>
      </MotionHeight>
      {isSuperuser && detailsOpen && (
        <CaseDetailsDialog caseId={clinicalCase.id} onClose={() => setDetailsOpen(false)} />
      )}
    </article>
  );
};
