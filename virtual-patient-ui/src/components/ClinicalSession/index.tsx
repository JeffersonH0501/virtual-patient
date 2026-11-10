import {FC, useState} from 'react';
import {useNavigate} from 'react-router-dom';
import {useTranslation} from 'react-i18next';
import {ActionButtons} from './ActionButtons';
import {ROUTES, type CalibrationRouteState} from '../../utils/routes';
import type {ClinicalCaseSimplified} from '../../services/clinicalCases';
import {useSessionList} from '../../contexts/SessionLists';
import {CustomSelect} from '../common';

type Props = {
  clinicalCase: ClinicalCaseSimplified;
  onView?: () => void;
  onCancel?: () => void;
};

type ReadOnlyFieldProps = {
  label: string;
  value: string;
};

const ReadOnlyField: FC<ReadOnlyFieldProps> = ({label, value}) => (
  <div className="ui-field">
    <span className="ui-field-label">{label}</span>
    <div className="ui-field-value truncate">
      {value}
    </div>
  </div>
);

export const ClinicalSession: FC<Props> = ({clinicalCase, onView, onCancel}) => {
  const {t} = useTranslation();
  const [personalityId, setPersonalityId] = useState<number | null>(null);
  const [gender, setGender] = useState<string>('');
  // The patient response language is fixed to Spanish and cannot be changed.
  const patientResponseLanguage = 'es';
  const {items: personalities = [], loading: isLoadingPersonalities} = useSessionList('personalities');
  const navigate = useNavigate();

  const personalityOptions = personalities.map((personality) => personality.name);
  const genderOptions = [t('clinicalSession.male'), t('clinicalSession.female')];
  const isFormValid = personalityId !== null && gender !== '';
  const configuration: CalibrationRouteState = {
    clinicalCaseId: clinicalCase.id,
    clinicalCaseTitle: clinicalCase.title,
    gender: gender || undefined,
    personalityId: personalityId ?? undefined,
    patientResponseLanguage,
  };

  const onStartSession = () => {
    if (!isFormValid) {
      return;
    }

    // The interview is not created here: it is only persisted once the
    // simulation actually starts, after calibration. Carry the configuration to
    // the calibration screen via location.state.
    navigate(ROUTES.calibration, {state: configuration});
  };

  return (
    <div className="ui-panel-body max-w-full overflow-x-clip">
      <div className="grid min-w-0 gap-x-layout gap-y-layout sm:grid-cols-3">
        <ReadOnlyField
          label={t('clinicalSession.patientResponseLanguage')}
          value={t('clinicalSession.spanish')}
        />

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
          />
        </div>
      </div>

      <ActionButtons
        onCancel={onCancel}
        onStartSession={onStartSession}
        isFormValid={isFormValid}
        onView={onView}
        onCalibrationPreview={onView ? () => navigate(ROUTES.calibration, {state: {...configuration, calibrationTest: true}}) : undefined}
        onGazePreview={onView ? () => navigate(ROUTES.calibration, {state: {...configuration, gazeTest: true}}) : undefined}
        onPreview={onView ? () => navigate(ROUTES.patientPreview, {
          state: {
            ...configuration,
            patientName: gender === 'female' ? clinicalCase.femaleName : clinicalCase.maleName,
            patientAge: clinicalCase.age,
            patientWeight: clinicalCase.weightInKg,
            personality: personalities.find((item) => item.id === personalityId),
          },
        }) : undefined}
      />
    </div>
  );
};
