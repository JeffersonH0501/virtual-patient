import {FC} from 'react';
import {useTranslation} from 'react-i18next';
import {Patient} from '../../types';
import {TagGroup} from './TagGroup';
import {Personality} from '../../types/personality';

type PatientProfileProps = {
  patient: Patient;
  caseTitle?: string;
  personality?: Personality | null;
};

export const PatientProfile: FC<PatientProfileProps> = ({patient, caseTitle, personality}) => {
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
    <div className="max-h-patient-profile w-full min-w-0 overflow-x-hidden overflow-y-auto rounded-xl bg-white shadow-panel-subtle scrollbar-hidden [&>section:not(:first-child)]:mx-4">
      <div className="sticky top-0 z-10 flex min-h-12 items-center border-b border-slate-200 bg-white px-4">
        <h2 className="component-title py-3 text-left">
          {t('patientProfile.interviewSummary')}
        </h2>
      </div>
      <section className="border-b border-solid border-gray-100 px-4 pt-4">
        <dl className="space-y-2 pb-5 text-sm leading-profile">
          {caseTitle && (
            <div className="grid grid-cols-patient-details items-start gap-3">
              <dt className="text-left font-normal text-gray-500">{t('patientProfile.case')}:</dt>
              <dd className="min-w-0 break-words text-right font-normal text-gray-800">{caseTitle}</dd>
            </div>
          )}
          {patient.name && (
            <div className="grid grid-cols-patient-details items-start gap-3">
              <dt className="text-left font-normal text-gray-500">{t('patientProfile.name')}:</dt>
              <dd className="min-w-0 break-words text-right font-normal text-gray-800">{patient.name}</dd>
            </div>
          )}
            {Object.entries(patient.basicInfo)
              .filter(([, value]) => value && value !== '' && value !== 0)
              .map(([key, value]) => (
                <div key={key} className="grid grid-cols-patient-details items-start gap-3">
                  <dt className="text-left font-normal text-gray-500">{getFieldLabel(key)}:</dt>
                  <dd className="min-w-0 break-words text-right font-normal text-gray-800">{getFieldValue(key, value)}</dd>
                </div>
              ))}
          {personality && (
            <div className="grid grid-cols-patient-details items-start gap-3">
              <dt className="text-left font-normal text-gray-500">{t('patientProfile.personality')}:</dt>
              <dd className="min-w-0 break-words text-right font-normal text-gray-800">{personality.name}</dd>
            </div>
          )}
        </dl>
      </section>
      {patient.symptoms && patient.symptoms.length > 0 && (
        <section className="pt-5 pb-6 border-b border-solid border-gray-100">
          <h3 className="mb-4 text-left text-sm font-medium text-slate-600">{t('patientProfile.currentSymptoms')}</h3>
          <TagGroup tags={patient.symptoms} tone="warning" />
        </section>
      )}
      {patient.allergies && patient.allergies.length > 0 && (
        <section className="pt-5 pb-6 border-b border-solid border-gray-100">
          <h3 className="mb-4 text-left text-sm font-medium text-slate-600">{t('patientProfile.allergies')}</h3>
          <TagGroup tags={patient.allergies} />
        </section>
      )}
      {patient.diet && patient.diet.trim() !== '' && (
        <section className="pt-5 pb-6 border-b border-solid border-gray-100">
          <h3 className="mb-4 text-left text-sm font-medium text-slate-600">{t('patientProfile.diet')}</h3>
          <p className="text-sm leading-relaxed text-gray-700 bg-gray-50 p-3 rounded-lg text-left">
            {patient.diet}
          </p>
        </section>
      )}
      {patient.illnesses && patient.illnesses.length > 0 && (
        <section className="pt-5 pb-6 border-b border-solid border-gray-100">
          <h3 className="mb-4 text-left text-sm font-medium text-slate-600">{t('patientProfile.currentIllnesses')}</h3>
          <div className="space-y-2">
            {patient.illnesses.map((illness, index) => (
              <div key={index} className="p-3 bg-gray-50 rounded-lg">
                <div className="flex justify-between items-start mb-2">
                  <h4 className="text-sm font-semibold text-gray-800">{illness.illness}</h4>
                  {illness.status && (
                    <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-normal text-slate-700">
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
          <h3 className="mb-4 text-left text-sm font-medium text-slate-600">{t('patientProfile.medications')}</h3>
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
          <h3 className="mb-4 text-left text-sm font-medium text-slate-600">{t('patientProfile.familyHistory')}</h3>
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
          <h3 className="mb-4 text-left text-sm font-medium text-slate-600">{t('patientProfile.habits')}</h3>
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
          <h3 className="mb-4 text-left text-sm font-medium text-slate-600">{t('patientProfile.workInformation')}</h3>
          <p className="text-sm leading-relaxed text-gray-700 bg-gray-50 p-3 rounded-lg text-left">
            {patient.workInformation}
          </p>
        </section>
      )}
      {patient.medicalHistory && patient.medicalHistory.length > 0 && (
        <section className="pt-5 pb-6 border-b border-solid border-gray-100">
          <h3 className="mb-4 text-left text-sm font-medium text-slate-600">{t('patientProfile.medicalHistory')}</h3>
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
          <h3 className="mb-4 text-left text-sm font-medium text-slate-600">{t('patientProfile.summary')}</h3>
          <p className="text-sm leading-relaxed text-gray-700 bg-gray-50 p-3 rounded-lg">
            {patient.summary}
          </p>
        </section>
      )}
    </div>
  );
};
