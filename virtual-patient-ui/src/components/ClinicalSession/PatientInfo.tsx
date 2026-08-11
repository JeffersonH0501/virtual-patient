import {FC} from 'react';
import {useTranslation} from 'react-i18next';
import type {ClinicalCaseSimplified} from '../../services/clinicalCases';
import patientImageM from '../../assets/patient_m.png';

type PatientInfoProps = {
  clinicalCase: ClinicalCaseSimplified;
};

export const PatientInfo: FC<PatientInfoProps> = ({clinicalCase}) => {
  const {t} = useTranslation();
  
  const getFallbackImage = () => {
    return patientImageM;
  };
  
  return (
    <div className="flex flex-col w-72 max-w-full">
      <h2 className="py-1.5 font-medium text-black text-left max-md:pr-5">{t('clinicalSession.patientInformation')}</h2>
      <div className="flex gap-4 pr-14 mt-2 leading-none text-black max-md:pr-5">
        <img
          loading="lazy"
          src={clinicalCase.femalePhoto || clinicalCase.malePhoto || getFallbackImage()}
          className="object-contain shrink-0 w-20 rounded-full aspect-square"
          alt="Patient profile"
        />
        <div className="flex flex-col items-start self-start py-1.5">
          <div className="mt-2.5">{clinicalCase.age} {t('clinicalSession.yearsOld')}</div>
          <div className="mt-2">Patient</div>
        </div>
      </div>
    </div>
  );
};
