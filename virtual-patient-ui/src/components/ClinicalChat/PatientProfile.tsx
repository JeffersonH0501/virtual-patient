import {FC} from 'react';
import {useTranslation} from 'react-i18next';
import {Patient} from '../../types';
import {TagGroup} from './TagGroup';
import {StatusIndicator, Button} from '../common';
import {RefreshIcon} from '../../icons';
import {Personality} from '../../types/personality';

type PatientProfileProps = {
  patient: Patient;
  caseTitle?: string;
  onRefreshSummary?: () => void;
  isLoading?: boolean;
  interviewStatus?: string;
  personality?: Personality | null;
  interviewId: number;
};

export const PatientProfile: FC<PatientProfileProps> = ({patient, caseTitle, onRefreshSummary, isLoading, interviewStatus, personality, interviewId}) => {
  const {t} = useTranslation();

  const getFieldLabel = (key: string): string => {
    switch (key) {
      case 'age':
        return t('patientProfile.age');
      case 'gender':
        return t('patientProfile.gender');
      case 'weight':
        return t('patientProfile.weight');
      case 'bloodType':
        return t('patientProfile.bloodType');
      default:
        return key.charAt(0).toUpperCase() + key.slice(1);
    }
  };

  const getFieldValue = (key: string, value: string | number): string | number => {
    if (key === 'gender') {
      if (value === 'male') {
        return t('clinicalSession.male');
      } else if (value === 'female') {
        return t('clinicalSession.female');
      }
    }
    return value;
  };
  
  return (
    <aside className="p-6 w-80 rounded-xl shadow-[0_1px_2px_rgba(0,0,0,0.05)] bg-white max-md:w-full">
      <section className="relative text-center border-b border-solid border-b-gray-200 pb-6">
        {onRefreshSummary && (
          <div className="absolute top-0 right-0" title={t('clinicalChat.refreshSummary')}>
            <Button
              onClick={onRefreshSummary}
              variant="ghost"
              size="sm"
              disabled={isLoading}
              className="flex items-center gap-1 p-1 !bg-blue-100 hover:!bg-blue-200 !text-blue-700 !focus:outline-none !focus:ring-2 !focus:ring-blue-500 !focus:ring-offset-2 !active:ring-2 !active:ring-blue-500 !active:ring-offset-2"
            >
              <RefreshIcon color="#2563eb" size={14} />
            </Button>
          </div>
        )}
        <div className="relative inline-block">
          <img
            src={patient.avatar}
            alt={patient.name}
            className="block mx-auto my-0 w-32 h-32 rounded-full border-4 border-gray-100 border-solid"
          />
          {interviewStatus === 'completed' ? (
            <StatusIndicator status="completed" />
          ) : patient.online ? (
            <StatusIndicator status="online" />
          ) : (
            <StatusIndicator status="offline" />
          )}
        </div>
        <h2 className="mt-6 text-xl font-bold text-gray-800">{patient.name}</h2>
        {caseTitle && (
          <p className="mt-2 text-base text-gray-500">{caseTitle}</p>
        )}
        {interviewId && (
          <p className="mt-1 text-sm text-gray-400">{t('patientProfile.interviewId')}: {interviewId}</p>
        )}
      </section>
      {Object.values(patient.basicInfo).some(value => value && value !== '' && value !== 0) && (
        <section className="pt-5 pb-4 border-b border-solid border-gray-100">
          <h3 className="mb-4 text-base font-bold text-gray-600 text-left">{t('patientProfile.basicInformation')}</h3>
          <dl>
            {Object.entries(patient.basicInfo)
              .filter(([, value]) => value && value !== '' && value !== 0)
              .map(([key, value]) => (
                <div key={key} className="flex justify-between mb-2">
                  <dt className="text-gray-500">{getFieldLabel(key)}:</dt>
                  <dd className="text-gray-800">{getFieldValue(key, value)}</dd>
                </div>
              ))}
          </dl>
        </section>
      )}
      {personality && (
        <section className="pt-5 pb-4 border-b border-solid border-gray-100">
          <h3 className="mb-4 text-base font-bold text-gray-600 text-left">{t('patientProfile.personality')}</h3>
          <div className="p-3 bg-blue-50 rounded-lg">
            <p className="text-sm text-blue-800 font-medium">{personality.name}</p>
          </div>
        </section>
      )}
      {patient.symptoms && patient.symptoms.length > 0 && (
        <section className="pt-5 pb-6 border-b border-solid border-gray-100">
          <h3 className="mb-4 text-base text-gray-600 text-left font-bold">{t('patientProfile.currentSymptoms')}</h3>
          <TagGroup tags={patient.symptoms} />
        </section>
      )}
      {patient.allergies && patient.allergies.length > 0 && (
        <section className="pt-5 pb-6 border-b border-solid border-gray-100">
          <h3 className="mb-4 text-base text-gray-600 text-left font-bold">{t('patientProfile.allergies')}</h3>
          <TagGroup tags={patient.allergies} />
        </section>
      )}
      {patient.diet && patient.diet.trim() !== '' && (
        <section className="pt-5 pb-6 border-b border-solid border-gray-100">
          <h3 className="mb-4 text-base text-gray-600 text-left font-bold">{t('patientProfile.diet')}</h3>
          <p className="text-sm leading-relaxed text-gray-700 bg-gray-50 p-3 rounded-lg text-left">
            {patient.diet}
          </p>
        </section>
      )}
      {patient.illnesses && patient.illnesses.length > 0 && (
        <section className="pt-5 pb-6 border-b border-solid border-gray-100">
          <h3 className="mb-4 text-base text-gray-600 text-left font-bold">{t('patientProfile.currentIllnesses')}</h3>
          <div className="space-y-2">
            {patient.illnesses.map((illness, index) => (
              <div key={index} className="p-3 bg-gray-50 rounded-lg">
                <div className="flex justify-between items-start mb-2">
                  <h4 className="text-sm font-semibold text-gray-800">{illness.illness}</h4>
                  {illness.status && (
                    <span className={`text-xs px-2 py-1 rounded-full font-medium ${
                      illness.status === 'Controlled' ? 'bg-green-100 text-green-800' : 
                      illness.status === 'Active' ? 'bg-red-100 text-red-800' : 
                      'bg-yellow-100 text-yellow-800'
                    }`}>
                      {illness.status}
                    </span>
                  )}
                </div>
                <div className="space-y-1">
                  {illness.diagnosisDate && (
                    <div>
                      <span className="text-xs font-medium text-gray-600">{t('patientProfile.diagnosed')}</span>
                      <span className="text-xs text-gray-700 ml-1">{illness.diagnosisDate}</span>
                    </div>
                  )}
                  {illness.severity && (
                    <div>
                      <span className="text-xs font-medium text-gray-600">{t('patientProfile.severity')}</span>
                      <span className="text-xs text-gray-700 ml-1">{illness.severity}</span>
                    </div>
                  )}
                  {illness.treatment && (
                    <div>
                      <span className="text-xs font-medium text-gray-600">{t('patientProfile.treatment')}</span>
                      <span className="text-xs text-gray-700 ml-1">{illness.treatment}</span>
                    </div>
                  )}
                  {illness.notes && (
                    <div>
                      <span className="text-xs font-medium text-gray-600">{t('patientProfile.notes')}</span>
                      <p className="text-xs text-gray-700 mt-1 leading-relaxed">{illness.notes}</p>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
      {patient.medications && patient.medications.length > 0 && (
        <section className="pt-5 pb-6 border-b border-solid border-gray-100">
          <h3 className="mb-4 text-base text-gray-600 text-left font-bold">{t('patientProfile.medications')}</h3>
          <div className="space-y-2">
            {patient.medications.map((medication, index) => (
              <div key={index} className="p-3 bg-gray-50 rounded-lg">
                <div className="mb-2">
                  <h4 className="text-sm font-semibold text-gray-800">{medication.medication}</h4>
                </div>
                <div className="space-y-1">
                  {medication.dosage && (
                    <div>
                      <span className="text-xs font-medium text-gray-600">{t('patientProfile.dosage')}</span>
                      <span className="text-xs text-gray-700 ml-1">{medication.dosage}</span>
                    </div>
                  )}
                  {medication.frequency && (
                    <div>
                      <span className="text-xs font-medium text-gray-600">{t('patientProfile.frequency')}</span>
                      <span className="text-xs text-gray-700 ml-1">{medication.frequency}</span>
                    </div>
                  )}
                  {medication.duration && (
                    <div>
                      <span className="text-xs font-medium text-gray-600">{t('patientProfile.duration')}</span>
                      <span className="text-xs text-gray-700 ml-1">{medication.duration}</span>
                    </div>
                  )}
                  {medication.purpose && (
                    <div>
                      <span className="text-xs font-medium text-gray-600">{t('patientProfile.purpose')}</span>
                      <span className="text-xs text-gray-700 ml-1">{medication.purpose}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
      {patient.familyHistory && patient.familyHistory.length > 0 && (
        <section className="pt-5 pb-6 border-b border-solid border-gray-100">
          <h3 className="mb-4 text-base text-gray-600 text-left font-bold">{t('patientProfile.familyHistory')}</h3>
          <div className="space-y-2">
            {patient.familyHistory.map((familyMember, index) => (
              <div key={index} className="p-3 bg-gray-50 rounded-lg">
                <div className="mb-2">
                  <h4 className="text-sm font-semibold text-gray-800">{familyMember.relationship}</h4>
                </div>
                <div className="space-y-1">
                  <div>
                    <span className="text-xs font-medium text-gray-600">{t('patientProfile.condition')}</span>
                    <span className="text-xs text-gray-700 ml-1">{familyMember.condition}</span>
                  </div>
                  {familyMember.notes && (
                    <div>
                      <span className="text-xs font-medium text-gray-600">{t('patientProfile.notes')}</span>
                      <span className="text-xs text-gray-700 ml-1">{familyMember.notes}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
      {patient.habits && patient.habits.length > 0 && (
        <section className="pt-5 pb-6 border-b border-solid border-gray-100">
          <h3 className="mb-4 text-base text-gray-600 text-left font-bold">{t('patientProfile.habits')}</h3>
          <div className="space-y-2">
            {patient.habits.map((habit, index) => (
              <div key={index} className="p-3 bg-gray-50 rounded-lg">
                <div className="mb-2">
                  <h4 className="text-sm font-semibold text-gray-800">{habit.habit}</h4>
                </div>
                <div className="space-y-1">
                  {habit.duration && (
                    <div>
                      <span className="text-xs font-medium text-gray-600">{t('patientProfile.duration')}</span>
                      <span className="text-xs text-gray-700 ml-1">{habit.duration}</span>
                    </div>
                  )}
                  {habit.frequency && (
                    <div>
                      <span className="text-xs font-medium text-gray-600">{t('patientProfile.frequency')}</span>
                      <span className="text-xs text-gray-700 ml-1">{habit.frequency}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
      {patient.workInformation && patient.workInformation.trim() !== '' && (
        <section className="pt-5 pb-6 border-b border-solid border-gray-100">
          <h3 className="mb-4 text-base text-gray-600 text-left font-bold">{t('patientProfile.workInformation')}</h3>
          <p className="text-sm leading-relaxed text-gray-700 bg-gray-50 p-3 rounded-lg text-left">
            {patient.workInformation}
          </p>
        </section>
      )}
      {patient.medicalHistory && patient.medicalHistory.length > 0 && (
        <section className="pt-5 pb-6 border-b border-solid border-gray-100">
          <h3 className="mb-4 text-base text-gray-600 text-left font-bold">{t('patientProfile.medicalHistory')}</h3>
          <div className="space-y-2">
            {patient.medicalHistory.map((history, index) => (
              <div key={index} className="p-3 bg-gray-50 rounded-lg">
                <div className="mb-2">
                  <h4 className="text-sm font-semibold text-gray-800">{history.type}</h4>
                </div>
                <div className="space-y-1">
                  {history.date && (
                    <div>
                      <span className="text-xs font-medium text-gray-600">{t('patientProfile.date')}</span>
                      <span className="text-xs text-gray-700 ml-1">{history.date}</span>
                    </div>
                  )}
                  {history.description && (
                    <div>
                      <span className="text-xs font-medium text-gray-600">{t('patientProfile.description')}</span>
                      <p className="text-xs text-gray-700 mt-1 leading-relaxed">{history.description}</p>
                    </div>
                  )}
                  {history.outcome && (
                    <div>
                      <span className="text-xs font-medium text-gray-600">{t('patientProfile.outcome')}</span>
                      <span className="text-xs text-gray-700 ml-1">{history.outcome}</span>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}
      {patient.summary && (
        <section className="pt-5 pb-6 text-left">
          <h3 className="mb-4 text-base text-gray-600 text-left font-bold">{t('patientProfile.summary')}</h3>
          <p className="text-sm leading-relaxed text-gray-700 bg-gray-50 p-3 rounded-lg">
            {patient.summary}
          </p>
        </section>
      )}
    </aside>
  );
};
