import {FC} from 'react';
import {useTranslation} from 'react-i18next';
import type {ClinicalCaseSimplified} from '../../services/clinicalCases';

type CaseDescriptionProps = {
  clinicalCase: ClinicalCaseSimplified;
};

export const CaseDescription: FC<CaseDescriptionProps> = ({clinicalCase}) => {
  const {t} = useTranslation();
  
  return (
    <div className="flex flex-col mt-6 text-black">
      <h2 className="py-1 w-72 max-w-full font-medium max-md:pr-5 text-left">
        {t('clinicalSession.clinicalCaseDescription')}
      </h2>
      <div className="z-10 px-5 pt-2.5 pb-4 mt-3.5 mb-0 bg-gray-50 rounded-lg max-md:px-5 max-md:mr-0 max-md:mb-2.5 text-left">
        {clinicalCase.description}
      </div>
    </div>
  );
};
