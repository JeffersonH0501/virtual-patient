import {Badge} from '../common/Badge';
import {FC, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {CaseCard} from './CaseCard';
import {ClinicalCasesLoading} from './ClinicalCasesLoading';
import {useSessionList} from '../../contexts/SessionLists';
import {useUser} from '../../hooks';
import {PageHeader} from '../common/PageHeader';
import {MotionHeight} from '../common/Motion';

export const ClinicalCases: FC = () => {
  const {t} = useTranslation();
  const {user} = useUser();
  const {items, loading, error} = useSessionList('cases', Boolean(user));
  const defaultCases = items ?? [];
  const isLoading = loading && items === undefined;
  const [expandedCaseId, setExpandedCaseId] = useState<number | null>(null);
  return (
    <section className="ui-page" aria-busy={isLoading}>
      <PageHeader eyebrow={t('clinicalCases.caseLibrary')} title={t(user?.role === 'student' ? 'clinicalCases.selectCaseToBegin' : 'clinicalCases.caseList')}>
        <Badge tone="info" className="shrink-0">
          {isLoading ? t('common.loading') : t('clinicalCases.availableCount', {count: defaultCases.length})}
        </Badge>
      </PageHeader>
      <MotionHeight fade={false}>
        {isLoading ? <ClinicalCasesLoading /> : error ? (
          <div className="p-inset text-danger-600 default-text" role="alert">
            {t('clinicalCases.failedToLoad')}
          </div>
        ) : (
          <div className="flex min-w-0 flex-col gap-layout">
            {defaultCases.map((clinicalCase, index) => (
              <CaseCard
                key={clinicalCase.id}
                clinicalCase={clinicalCase}
                caseIndex={index + 1}
                expanded={expandedCaseId === clinicalCase.id}
                onToggle={() =>
                  setExpandedCaseId((currentId) =>
                    currentId === clinicalCase.id ? null : clinicalCase.id,
                  )
                }
              />
            ))}
          </div>
        )}
      </MotionHeight>
    </section>
  );
};

