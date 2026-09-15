import {FC, useEffect, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {useLocation} from 'react-router-dom';
import {CaseCard} from './CaseCard';
import {CustomCaseCard} from './CustomCaseCard';
import {ClinicalCasesSkeleton} from './ClinicalCasesSkeleton';
import {
  getDefaultCases,
  getCasesByOrganization,
  ClinicalCaseSimplified,
} from '../../services/clinicalCases';
import {useUser} from '../../hooks';

export const ClinicalCases: FC = () => {
  const {t} = useTranslation();
  const {user} = useUser();
  const location = useLocation();
  const [defaultCases, setDefaultCases] = useState<ClinicalCaseSimplified[]>([]);
  const [customCases, setCustomCases] = useState<ClinicalCaseSimplified[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedCaseId, setExpandedCaseId] = useState<number | null>(null);

  const fetchCases = async () => {
    try {
      setIsLoading(true);
      setError(null);

      // Fetch both default and custom cases in parallel
      const [defaultCasesData, customCasesData] = await Promise.all([
        getDefaultCases(),
        getCasesByOrganization('1'), // Using org ID 1 as default
      ]);

      setDefaultCases(defaultCasesData as ClinicalCaseSimplified[]);
      setCustomCases(customCasesData as ClinicalCaseSimplified[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('clinicalCases.failedToLoad'));
    } finally {
      setIsLoading(false);
    }
  };

  // Fetch cases on mount and when returning from edit/create
  useEffect(() => {
    fetchCases();
  }, [location.key]); // Re-fetch when location.key changes (navigation occurs)

  if (isLoading) {
    return <ClinicalCasesSkeleton />;
  }

  if (error) {
    return (
      <div className="flex justify-center items-center min-h-loading-state">
        <div className="text-lg text-red-600">{error}</div>
      </div>
    );
  }

  const availableCaseCount = defaultCases.length + customCases.length;

  return (
    <section className="mx-auto w-full max-w-content overflow-x-clip text-left">
      <div className="flex flex-col items-start gap-3 border-b border-slate-200 pb-4 sm:mt-2 sm:flex-row sm:items-end sm:justify-between sm:gap-4">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-eyebrow text-slate-500">
            {t('clinicalCases.caseLibrary')}
          </p>
          <h2 className="mt-1 text-xl font-semibold leading-7 tracking-tight text-slate-900 md:text-2xl">
            {user?.role === 'student'
              ? t('clinicalCases.selectCaseToBegin')
              : t('clinicalCases.selectOrCreate')}
          </h2>
        </div>
        <div className="shrink-0 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs font-medium text-slate-500">
          {t('clinicalCases.availableCount', {count: availableCaseCount})}
        </div>
      </div>
      <div className="mt-4 w-full min-w-0 self-stretch sm:mt-5">
        <div className="flex min-w-0 flex-col gap-3">
          {defaultCases.map((caseData, index) => (
            <CaseCard
              key={caseData.id}
              type="Default"
              clinicalCase={caseData}
              caseIndex={index + 1}
              expanded={expandedCaseId === caseData.id}
              onToggle={() =>
                setExpandedCaseId((currentId) =>
                  currentId === caseData.id ? null : caseData.id,
                )
              }
            />
          ))}
          {customCases.map((caseData, index) => (
            <CaseCard
              key={caseData.id}
              type="Custom"
              clinicalCase={caseData}
              caseIndex={defaultCases.length + index + 1}
              expanded={expandedCaseId === caseData.id}
              onToggle={() =>
                setExpandedCaseId((currentId) =>
                  currentId === caseData.id ? null : caseData.id,
                )
              }
            />
          ))}
          {(user?.role === 'teacher' || user?.role === 'superuser') && <CustomCaseCard />}
        </div>
      </div>
    </section>
  );
};
