import {FC, useEffect, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {useLocation} from 'react-router-dom';
import {CaseCard} from './CaseCard';
import {CustomCaseCard} from './CustomCaseCard';
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
    return (
      <div className="flex justify-center items-center min-h-[200px]">
        <div className="text-lg text-gray-600">{t('clinicalCases.loadingCases')}</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex justify-center items-center min-h-[200px]">
        <div className="text-lg text-red-600">{error}</div>
      </div>
    );
  }

  return (
    <>
      <p className="mt-4 text-xl font-medium text-black max-md:max-w-full">
        {user?.role === 'student' ? t('clinicalCases.selectCaseToBegin') : t('clinicalCases.selectOrCreate')}
      </p>
      <div className="self-stretch mt-10 max-md:mt-10 max-md:max-w-full">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-10 items-stretch">
          {defaultCases.map((caseData, index) => (
            <CaseCard key={caseData.id} type="Default" clinicalCase={caseData} caseIndex={index + 1} />
          ))}
          {customCases.map((caseData, index) => (
            <CaseCard key={caseData.id} type="Custom" clinicalCase={caseData} caseIndex={defaultCases.length + index + 1} />
          ))}
          {(user?.role === 'teacher' || user?.role === 'superuser') && <CustomCaseCard />}
        </div>
      </div>
    </>
  );
};
