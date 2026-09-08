import {FC, useEffect, useState} from 'react';
import {useNavigate} from 'react-router-dom';
import {useTranslation} from 'react-i18next';
import {ActionButtons} from './ActionButtons';
import {interviewPath} from '../../utils/routes';
import type {ClinicalCaseSimplified} from '../../services/clinicalCases';
import {createInterview} from '../../services/interviews/createInterview';
import {getPersonalities} from '../../services/personalities';
import {CustomSelect} from '../common';
import {Personality} from '../../types';

type Props = {
  clinicalCase: ClinicalCaseSimplified;
  onCancel: () => void;
};

type ReadOnlyFieldProps = {
  label: string;
  value: string;
};

const ReadOnlyField: FC<ReadOnlyFieldProps> = ({label, value}) => (
  <div className="min-w-0">
    <p className="mb-3 text-left text-sm text-black">{label}</p>
    <div className="min-h-12 truncate rounded-xl border border-slate-300 bg-slate-100 px-3 py-3 text-sm text-slate-700">
      {value}
    </div>
  </div>
);

export const ClinicalSession: FC<Props> = ({clinicalCase, onCancel}) => {
  const {t} = useTranslation();
  const [personalityId, setPersonalityId] = useState<number | null>(null);
  const [gender, setGender] = useState<string>('');
  const [patientResponseLanguage, setPatientResponseLanguage] = useState<'en' | 'es' | ''>('');
  const [personalities, setPersonalities] = useState<Personality[]>([]);
  const [isLoadingPersonalities, setIsLoadingPersonalities] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchPersonalities = async () => {
      try {
        const personalitiesData = await getPersonalities();
        setPersonalities(personalitiesData);
      } catch (error) {
        console.error('Failed to fetch personalities:', error);
      } finally {
        setIsLoadingPersonalities(false);
      }
    };

    fetchPersonalities();
  }, []);

  const personalityOptions = personalities.map((personality) => personality.name);
  const genderOptions = [t('clinicalSession.male'), t('clinicalSession.female')];
  const patientAge = clinicalCase.age
    ? t('clinicalCases.ageValue', {age: clinicalCase.age})
    : t('clinicalCases.notSpecified');
  const isFormValid =
    personalityId !== null && gender !== '' && patientResponseLanguage !== '';

  const onStartSession = async () => {
    if (!isFormValid) {
      return;
    }

    const interview = await createInterview({
      clinical_case_id: clinicalCase.id.toString(),
      patient_response_language: patientResponseLanguage || 'en',
      patient_gender: gender || undefined,
      personality_id: personalityId || undefined,
    });
    if (!interview) return;

    navigate(interviewPath(interview.id, 'session'));
  };

  return (
    <div className="min-w-0 max-w-full overflow-x-clip p-4 sm:p-5">
      <h4 className="mb-4 text-sm font-semibold text-slate-800">
        {t('clinicalSession.patientInformation')}
      </h4>
      <div className="grid min-w-0 gap-x-4 gap-y-4 sm:grid-cols-2">
        <ReadOnlyField label={t('clinicalCases.patientAge')} value={patientAge} />

        <div className="min-w-0">
          <CustomSelect
            label={t('clinicalSession.personality')}
            id={`personality-${clinicalCase.id}`}
            placeholder={
              isLoadingPersonalities
                ? t('clinicalSession.loadingPersonalities')
                : t('clinicalSession.selectPersonality')
            }
            value={
              personalityId
                ? personalities.find((personality) => personality.id === personalityId)?.name ||
                  ''
                : ''
            }
            onChange={(value) => {
              const selectedPersonality = personalities.find(
                (personality) => personality.name === value,
              );
              setPersonalityId(selectedPersonality?.id || null);
            }}
            options={personalityOptions}
            disabled={isLoadingPersonalities}
            margin={false}
          />
        </div>

        <div className="min-w-0">
          <CustomSelect
            label={t('clinicalSession.gender')}
            id={`gender-${clinicalCase.id}`}
            placeholder={t('clinicalSession.selectGender')}
            value={
              gender === 'male'
                ? t('clinicalSession.male')
                : gender === 'female'
                  ? t('clinicalSession.female')
                  : gender
            }
            onChange={(value) => {
              const genderValue =
                value === t('clinicalSession.male')
                  ? 'male'
                  : value === t('clinicalSession.female')
                    ? 'female'
                    : value;
              setGender(genderValue);
            }}
            options={genderOptions}
            margin={false}
          />
        </div>

        <div className="min-w-0">
          <CustomSelect
            label={t('clinicalSession.patientResponseLanguage')}
            id={`patient-response-language-${clinicalCase.id}`}
            placeholder={t('clinicalSession.selectPatientResponseLanguage')}
            value={
              patientResponseLanguage === 'en'
                ? t('clinicalSession.english')
                : patientResponseLanguage === 'es'
                  ? t('clinicalSession.spanish')
                  : ''
            }
            onChange={(value) => {
              setPatientResponseLanguage(
                value === t('clinicalSession.spanish') ? 'es' : 'en',
              );
            }}
            options={[t('clinicalSession.english'), t('clinicalSession.spanish')]}
            margin={false}
          />
        </div>
      </div>

      <ActionButtons
        onCancel={onCancel}
        onStartSession={onStartSession}
        isFormValid={isFormValid}
      />
    </div>
  );
};
