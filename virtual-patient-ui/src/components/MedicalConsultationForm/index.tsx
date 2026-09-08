import {useState, ChangeEvent, FormEvent, FC, useEffect} from 'react';
import {useNavigate, useParams} from 'react-router-dom';
import {useTranslation} from 'react-i18next';
import {FormSection} from './FormSection';
import {HealthIcon, InfoIcon} from '../../icons';
import {FormInput, CustomSelect} from '../common';
import {
  createClinicalCase,
  updateClinicalCase,
  getClinicalCaseById,
  CreateClinicalCasePayload,
} from '../../services/clinicalCases';
import {ROUTES} from '../../utils/routes';

// Form data uses strings for all fields (for form inputs)
type FormData = {
  title: string;
  description: string;
  age: string;
  femaleName: string;
  maleName: string;
  genderRestriction: string;
  weightInKg: string;
  physicalRequirements: string;
  socioeconomicStatus: string;
  patientContext: string;
  chiefComplaint: string;
  presentIllness: string;
  personalMedicalHistory: string;
  surgicalHistory: string;
  familyHistory: string;
  medications: string;
  habits: string;
  allergies: string;
  concerns: string;
};

type MedicalConsultationFormProps = {
  mode?: 'create' | 'edit';
};

export const MedicalConsultationForm: FC<MedicalConsultationFormProps> = ({mode = 'create'}) => {
  const {t} = useTranslation();
  const {caseId} = useParams<{caseId: string}>();
  const navigate = useNavigate();
  const [formData, setFormData] = useState<FormData>({
    title: '',
    description: '',
    age: '',
    femaleName: '',
    maleName: '',
    genderRestriction: '',
    weightInKg: '',
    physicalRequirements: '',
    socioeconomicStatus: '',
    patientContext: '',
    chiefComplaint: '',
    presentIllness: '',
    personalMedicalHistory: '',
    surgicalHistory: '',
    familyHistory: '',
    medications: '',
    habits: '',
    allergies: '',
    concerns: '',
  });

  const [isLoading, setIsLoading] = useState(false);
  const [isFetching, setIsFetching] = useState(mode === 'edit');
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  // Fetch existing case data in edit mode
  useEffect(() => {
    const fetchCaseData = async () => {
      if (mode === 'edit' && caseId) {
        try {
          setIsFetching(true);
          setError(null);
          const caseData = await getClinicalCaseById(caseId);
          setFormData({
            title: caseData.title || '',
            description: caseData.description || '',
            age: caseData.age?.toString() || '',
            femaleName: caseData.femaleName || '',
            maleName: caseData.maleName || '',
            genderRestriction: caseData.genderRestriction || '',
            weightInKg: caseData.weightInKg?.toString() || '',
            physicalRequirements: caseData.physicalRequirements || '',
            socioeconomicStatus: caseData.socioeconomicStatus || '',
            patientContext: caseData.patientContext || '',
            chiefComplaint: caseData.chiefComplaint || '',
            presentIllness: caseData.presentIllness || '',
            personalMedicalHistory: caseData.personalMedicalHistory || '',
            surgicalHistory: caseData.surgicalHistory || '',
            familyHistory: caseData.familyHistory || '',
            medications: caseData.medications || '',
            habits: caseData.habits || '',
            allergies: caseData.allergies || '',
            concerns: caseData.concerns || '',
          });
        } catch (err) {
          setError(err instanceof Error ? err.message : t('createCase.failedToLoad'));
        } finally {
          setIsFetching(false);
        }
      }
    };

    fetchCaseData();
  }, [mode, caseId, t]);

  // Update form data with translated default values when language changes (only for create mode)
  useEffect(() => {
    if (mode === 'create') {
      setFormData(prev => ({
        ...prev,
        socioeconomicStatus: prev.socioeconomicStatus || t('createCase.lowIncome'),
      }));
    }
  }, [t, mode]);

  const handleInputChange =
    (field: keyof FormData) =>
    (e: ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
      setFormData((prev) => ({
        ...prev,
        [field]: e.target.value,
      }));
      // Clear error for this field when user starts typing
      if (fieldErrors[field]) {
        setFieldErrors((prev) => {
          const newErrors = { ...prev };
          delete newErrors[field];
          return newErrors;
        });
      }
    };

  const handleSelectChange = (field: keyof FormData) => (value: string) => {
    setFormData((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  const isFormValid = () => {
    // Check all fields except hidden ones based on gender restriction
    const fieldsToCheck: (keyof FormData)[] = Object.keys(formData) as (keyof FormData)[];
    
    for (const field of fieldsToCheck) {
      const value = formData[field];
      
      // Skip hidden fields based on gender restriction
      if (formData.genderRestriction === 'male' && field === 'femaleName') {
        continue; // Skip femaleName when restriction is male
      }
      if (formData.genderRestriction === 'female' && field === 'maleName') {
        continue; // Skip maleName when restriction is female
      }
      
      // genderRestriction is optional, so skip validation for it
      if (field === 'genderRestriction') {
        continue;
      }
      
      // Validate required fields
      if (typeof value === 'string') {
        if (value.trim() === '') {
          return false;
        }
      } else if (value === null || value === undefined) {
        return false;
      }
    }
    
    return true;
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();

    // Clear previous field errors
    setFieldErrors({});
    setError(null);

    if (!isFormValid()) {
      // Find which fields are missing and set field-specific errors
      const newFieldErrors: Record<string, string> = {};
      const fieldsToCheck: (keyof FormData)[] = Object.keys(formData) as (keyof FormData)[];
      
      for (const field of fieldsToCheck) {
        const value = formData[field];
        
        // Skip hidden fields based on gender restriction
        if (formData.genderRestriction === 'male' && field === 'femaleName') {
          continue;
        }
        if (formData.genderRestriction === 'female' && field === 'maleName') {
          continue;
        }
        
        // Skip optional fields
        if (field === 'genderRestriction') {
          continue;
        }
        
        // Check if field is empty
        if (typeof value === 'string' && value.trim() === '') {
          newFieldErrors[field] = t('createCase.fieldRequired');
        } else if (value === null || value === undefined) {
          newFieldErrors[field] = t('createCase.fieldRequired');
        }
      }
      
      setFieldErrors(newFieldErrors);
      setError(t('createCase.fillAllFields'));
      return;
    }

    setIsLoading(true);
    setError(null);
    setFieldErrors({});

    try {
      const payload: CreateClinicalCasePayload = {
        ...formData,
        age: formData.age ? parseInt(formData.age, 10) : null,
        weightInKg: formData.weightInKg ? parseFloat(formData.weightInKg) : 0,
        femaleName: formData.femaleName || null,
        maleName: formData.maleName || null,
        physicalRequirements: formData.physicalRequirements,
        socioeconomicStatus: formData.socioeconomicStatus,
        patientContext: formData.patientContext,
        chiefComplaint: formData.chiefComplaint,
        presentIllness: formData.presentIllness,
        personalMedicalHistory: formData.personalMedicalHistory,
        surgicalHistory: formData.surgicalHistory,
        familyHistory: formData.familyHistory,
        medications: formData.medications,
        habits: formData.habits,
        allergies: formData.allergies,
        concerns: formData.concerns,
        caseType: 'custom',
        organizationId: 1,
      };

      if (mode === 'edit' && caseId) {
        await updateClinicalCase(caseId, payload);
      } else {
        await createClinicalCase(payload);
      }
      
      navigate(ROUTES.clinicalCases);
    } catch (err) {
      setError(
        err instanceof Error 
          ? err.message 
          : mode === 'edit' 
            ? t('createCase.failedToUpdate') 
            : t('createCase.failedToCreate')
      );
    } finally {
      setIsLoading(false);
    }
  };

  if (isFetching) {
    return (
      <div className="min-h-case-form w-full flex items-center justify-center">
        <div className="text-lg text-gray-600">{t('common.loading')}</div>
      </div>
    );
  }

  return (
    <div className="min-h-case-form w-full">
      <form
        onSubmit={handleSubmit}
        className="p-8 mx-auto my-0 max-w-6xl bg-white rounded-xl shadow-sm"
      >
        <div className="mb-6 p-4 bg-blue-50 border border-blue-200 rounded-lg">
          <div className="flex items-start">
            <p className="text-sm text-blue-800">
              {t('createCase.genderNeutralMessage')}
            </p>
          </div>
        </div>
        <FormSection icon={<InfoIcon />} title={t('createCase.introductoryInformation')}>
          <div className="grid grid-cols-2 gap-6 mb-6 max-md:grid-cols-1">
            <FormInput
              label={`${t('createCase.caseTitle')} *`}
              type="text"
              id="title"
              placeholder={t('createCase.enterCaseTitle')}
              value={formData.title}
              onChange={handleInputChange('title')}
              error={fieldErrors.title}
            />
            <FormInput
              label={`${t('createCase.caseDescription')} *`}
              type="textarea"
              id="description"
              placeholder={t('createCase.enterCaseDescription')}
              value={formData.description}
              onChange={handleInputChange('description')}
              error={fieldErrors.description}
            />
            {formData.genderRestriction !== 'male' && (
              <FormInput
                label={`${t('createCase.femaleName')} *`}
                type="text"
                id="femaleName"
                placeholder={t('createCase.enterFemaleName')}
                value={formData.femaleName}
                onChange={handleInputChange('femaleName')}
                error={fieldErrors.femaleName}
              />
            )}
            {formData.genderRestriction !== 'female' && (
              <FormInput
                label={`${t('createCase.maleName')} *`}
                type="text"
                id="maleName"
                placeholder={t('createCase.enterMaleName')}
                value={formData.maleName}
                onChange={handleInputChange('maleName')}
                error={fieldErrors.maleName}
              />
            )}
            <CustomSelect
              label={t('createCase.genderRestriction')}
              id="genderRestriction"
              placeholder={t('createCase.selectGenderRestriction')}
              value={formData.genderRestriction === '' ? t('createCase.noRestriction') : 
                     formData.genderRestriction === 'female' ? t('createCase.female') :
                     formData.genderRestriction === 'male' ? t('createCase.male') : 
                     formData.genderRestriction}
              onChange={(value) => {
                // Convert translated values to language-agnostic values
                const restrictionValue = value === t('createCase.noRestriction') ? '' :
                                        value === t('createCase.female') ? 'female' :
                                        value === t('createCase.male') ? 'male' :
                                        value;
                handleSelectChange('genderRestriction')(restrictionValue);
              }}
              options={[t('createCase.noRestriction'), t('createCase.female'), t('createCase.male')]}
            />
            <FormInput
              label={`${t('createCase.age')} *`}
              type="number"
              id="age"
              placeholder={t('createCase.enterAge')}
              value={formData.age}
              onChange={handleInputChange('age')}
              error={fieldErrors.age}
            />
            <FormInput
              label={`${t('createCase.weight')} *`}
              type="number"
              id="weightInKg"
              placeholder={t('createCase.enterWeight')}
              value={formData.weightInKg}
              onChange={handleInputChange('weightInKg')}
              error={fieldErrors.weightInKg}
            />
            <FormInput
              label={`${t('createCase.specialPhysicalRequirements')} *`}
              type="textarea"
              id="physicalRequirements"
              placeholder={t('createCase.enterPhysicalRequirements')}
              value={formData.physicalRequirements}
              onChange={handleInputChange('physicalRequirements')}
              error={fieldErrors.physicalRequirements}
            />
            <CustomSelect
              label={`${t('createCase.socioeconomicCondition')} *`}
              id="socioeconomicStatus"
              placeholder={t('createCase.selectSocioeconomicCondition')}
              value={formData.socioeconomicStatus}
              onChange={handleSelectChange('socioeconomicStatus')}
              options={[t('createCase.lowIncome'), t('createCase.middleIncome'), t('createCase.highIncome')]}
            />
            <FormInput
              label={`${t('createCase.patientContext')} *`}
              type="textarea"
              id="patientContext"
              placeholder={t('createCase.enterPatientContext')}
              value={formData.patientContext}
              onChange={handleInputChange('patientContext')}
              error={fieldErrors.patientContext}
            />
          </div>
        </FormSection>

        <FormSection icon={<HealthIcon />} title={t('createCase.healthSituation')}>
          <div className="grid grid-cols-2 gap-6 mb-6 max-md:grid-cols-1">
            <FormInput
              label={`${t('createCase.reasonForConsultation')} *`}
              type="textarea"
              id="chiefComplaint"
              placeholder={t('createCase.enterReasonForConsultation')}
              value={formData.chiefComplaint}
              onChange={handleInputChange('chiefComplaint')}
              error={fieldErrors.chiefComplaint}
            />
            <FormInput
              label={`${t('createCase.currentConsultation')} *`}
              type="textarea"
              id="presentIllness"
              placeholder={t('createCase.enterCurrentConsultation')}
              value={formData.presentIllness}
              onChange={handleInputChange('presentIllness')}
              error={fieldErrors.presentIllness}
            />
            <FormInput
              label={`${t('createCase.personalMedicalHistory')} *`}
              type="textarea"
              id="personalMedicalHistory"
              placeholder={t('createCase.enterPersonalMedicalHistory')}
              value={formData.personalMedicalHistory}
              onChange={handleInputChange('personalMedicalHistory')}
              error={fieldErrors.personalMedicalHistory}
            />
            <FormInput
              label={`${t('createCase.surgicalHistory')} *`}
              type="textarea"
              id="surgicalHistory"
              placeholder={t('createCase.enterSurgicalHistory')}
              value={formData.surgicalHistory}
              onChange={handleInputChange('surgicalHistory')}
              error={fieldErrors.surgicalHistory}
            />
            <FormInput
              label={`${t('createCase.familyMedicalHistory')} *`}
              type="textarea"
              id="familyHistory"
              placeholder={t('createCase.enterFamilyMedicalHistory')}
              value={formData.familyHistory}
              onChange={handleInputChange('familyHistory')}
              error={fieldErrors.familyHistory}
            />
            <FormInput
              label={`${t('createCase.medications')} *`}
              type="textarea"
              id="medications"
              placeholder={t('createCase.enterMedications')}
              value={formData.medications}
              onChange={handleInputChange('medications')}
              error={fieldErrors.medications}
            />
            <FormInput
              label={`${t('createCase.habits')} *`}
              type="textarea"
              id="habits"
              placeholder={t('createCase.enterHabits')}
              value={formData.habits}
              onChange={handleInputChange('habits')}
              error={fieldErrors.habits}
            />
            <FormInput
              label={`${t('createCase.allergies')} *`}
              type="textarea"
              id="allergies"
              placeholder={t('createCase.enterAllergies')}
              value={formData.allergies}
              onChange={handleInputChange('allergies')}
              error={fieldErrors.allergies}
            />
            <FormInput
              label={`${t('createCase.concerns')} *`}
              type="textarea"
              id="concerns"
              placeholder={t('createCase.enterConcerns')}
              value={formData.concerns}
              onChange={handleInputChange('concerns')}
              error={fieldErrors.concerns}
            />
          </div>
          {error && <div className="text-red-500 text-center mb-4">{error}</div>}
          <div className="flex justify-end mt-10 gap-8">
            <button
              type="button"
              className="px-8 py-4 text-base text-blue-600 rounded-xl border border-indigo-500 border-solid cursor-pointer min-w-form-action max-sm:w-full hover:bg-blue-50 transition-colors"
              onClick={() => window.history.back()}
            >
              {t('createCase.goBack')}
            </button>
            <button
              type="submit"
              className="px-8 py-4 text-base text-white bg-blue-600 rounded-lg cursor-pointer border-none min-w-form-action max-sm:w-full hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              disabled={isLoading || !isFormValid()}
            >
              {isLoading 
                ? t('createCase.submitting') 
                : mode === 'edit' 
                  ? t('createCase.updateCase') 
                  : t('createCase.submit')}
            </button>
          </div>
        </FormSection>
      </form>
    </div>
  );
};
