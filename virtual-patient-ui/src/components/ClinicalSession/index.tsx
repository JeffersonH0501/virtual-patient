import {FC, useState, useEffect} from 'react';
import {PatientInfo} from './PatientInfo';
import {CaseDescription} from './CaseDescription';
import {AssistantNameInput} from './AssistantNameInput';
import {ActionButtons} from './ActionButtons';
import {useNavigate} from 'react-router-dom';
import {ROUTES} from '../../utils/routes';
import type {ClinicalCaseSimplified} from '../../services/clinicalCases';
import {createInterview} from '../../services/interviews/createInterview';
import {getPersonalities} from '../../services/personalities';
import {CustomSelect} from '../common';
import {useTranslation} from 'react-i18next';
import {Personality} from '../../types';
import {useUser} from '../../hooks';

type Props = {
  clinicalCase: ClinicalCaseSimplified;
  caseIndex: number;
  onCancel: () => void;
};

export const ClinicalSession: FC<Props> = ({clinicalCase, caseIndex, onCancel}) => {
  const {t} = useTranslation();
  const {user} = useUser();
  const [assistantName, setAssistantName] = useState<string>('Dr. Berg');
  const [personalityId, setPersonalityId] = useState<number | null>(null);
  const [gender, setGender] = useState<string>(clinicalCase.genderRestriction || '');
  const [patientResponseLanguage, setPatientResponseLanguage] = useState<'en' | 'es' | ''>('');
  const [personalities, setPersonalities] = useState<Personality[]>([]);
  const [isLoadingPersonalities, setIsLoadingPersonalities] = useState(true);
  const navigate = useNavigate();

  // Set gender from restriction if present
  useEffect(() => {
    if (clinicalCase.genderRestriction) {
      setGender(clinicalCase.genderRestriction);
    }
  }, [clinicalCase.genderRestriction]);

  // Fetch personalities on component mount
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

  // Personality options from API
  const personalityOptions = personalities.map((personality) => personality.name);

  // Check if gender is restricted
  const hasGenderRestriction = !!clinicalCase.genderRestriction;
  const genderOptions = hasGenderRestriction
    ? [clinicalCase.genderRestriction === 'female' ? t('clinicalSession.female') : t('clinicalSession.male')]
    : [t('clinicalSession.male'), t('clinicalSession.female')];

  // Validation logic
  const isFormValid = () => {
    return personalityId !== null && gender !== '' && patientResponseLanguage !== '';
  };

  const onStartSession = async () => {
    if (!isFormValid()) {
      return; // Don't proceed if validation fails
    }

    const interview = await createInterview({
      clinical_case_id: clinicalCase.id.toString(),
      patient_response_language: patientResponseLanguage || 'en',
      patient_gender: gender || undefined,
      personality_id: personalityId || undefined,
    });
    if (!interview) return;

    navigate(ROUTES.clinicalChat + '/' + interview.id);
  };

  return (
    <div className="fixed inset-0 bg-opacity-50 overflow-y-auto h-full w-full flex items-center justify-center">
      <div className="flex flex-col rounded-2xl max-w-[796px] bg-white">
        <div className="flex flex-col pt-9 pr-2 pb-4 pl-10 w-full rounded-2xl shadow-[0px_8px_10px_rgba(0,0,0,0.1)] max-md:pl-5 max-md:max-w-full">
          <h2 className="self-start text-2xl font-semibold leading-none text-black">
            {t('clinicalSession.newSession', {
              caseTitle: user?.role === 'student' ? t('clinicalCases.clinicalCaseWithIndex', {index: caseIndex}) : clinicalCase.title,
            })}
          </h2>
          <div className="flex flex-col pr-5 pb-3 mt-9 w-full max-md:max-w-full">
            <div className="w-full max-w-[700px] max-md:max-w-full">
              <div className="flex gap-5 max-md:flex-col">
                <div className="flex flex-col w-[58%] max-md:ml-0 max-md:w-full">
                  <div className="flex flex-col grow pr-3.5 pb-5 w-full text-sm max-md:mt-5">
                    <PatientInfo clinicalCase={clinicalCase} />
                    <CaseDescription clinicalCase={clinicalCase} />
                  </div>
                </div>
                <div className="flex flex-col ml-5 w-[42%] max-md:ml-0 max-md:w-full">
                  <div className="flex flex-col pb-32 w-full max-md:pb-24 max-md:mt-5">
                    <AssistantNameInput name={assistantName} onNameChange={setAssistantName} />

                    {/* Patient Configuration Section */}
                    <div className="mt-6 space-y-4">
                      <h3 className="text-lg font-semibold text-gray-800">{t('clinicalSession.patientConfiguration')}</h3>

                      <CustomSelect
                        label={`${t('clinicalSession.personality')} *`}
                        id="personality"
                        placeholder={isLoadingPersonalities ? t('clinicalSession.loadingPersonalities') : t('clinicalSession.selectPersonality')}
                        value={personalityId ? personalities.find((p) => p.id === personalityId)?.name || '' : ''}
                        onChange={(value) => {
                          const selectedPersonality = personalities.find((p) => p.name === value);
                          setPersonalityId(selectedPersonality?.id || null);
                        }}
                        options={personalityOptions}
                        disabled={isLoadingPersonalities}
                      />

                      <CustomSelect
                        label={`${t('clinicalSession.gender')} *`}
                        id="gender"
                        placeholder={t('clinicalSession.selectGender')}
                        value={gender === 'male' ? t('clinicalSession.male') :
                               gender === 'female' ? t('clinicalSession.female') :
                               gender}
                        onChange={(value) => {
                          // Convert translated values to language-agnostic values
                          const genderValue = value === t('clinicalSession.male') ? 'male' :
                                            value === t('clinicalSession.female') ? 'female' :
                                            value;
                          setGender(genderValue);
                        }}
                        options={genderOptions}
                        disabled={hasGenderRestriction}
                      />

                      <CustomSelect
                        label={`${t('clinicalSession.patientResponseLanguage')} *`}
                        id="patient-response-language"
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
                        options={[
                          t('clinicalSession.english'),
                          t('clinicalSession.spanish'),
                        ]}
                      />

                    </div>
                  </div>
                </div>
              </div>
            </div>
            <ActionButtons onCancel={onCancel} onStartSession={onStartSession} isFormValid={isFormValid()} />
          </div>
        </div>
      </div>
    </div>
  );
};
