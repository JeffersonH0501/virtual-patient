export type CaseType = 'default' | 'custom';

export type CreatedByUser = {
  id: number;
  firstName: string;
  lastName: string;
};

export type ClinicalCaseBase = {
  id: number;
  title: string;
  description: string;
  caseType: CaseType;
  organizationId: number | null;
  active?: boolean;
  createdBy?: CreatedByUser | null; // Only for custom cases
  icon?: string | null;
  age: number | null;
  weightInKg?: number | null;
  femalePhoto?: string | null;
  malePhoto?: string | null;
  femaleName?: string | null;
  maleName?: string | null;
  genderRestriction?: string | null;
};


export type PatientFields = {
  weightInKg: number;
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

export type TranslatedClinicalCase = {
  titleTranslations: {
    es: string;
  };
  descriptionTranslations: {
    es: string;
  };
  chiefComplaintTranslations: {
    es: string;
  };
  presentIllnessTranslations: {
    es: string;
  };
  personalMedicalHistoryTranslations: {
    es: string;
  };
  surgicalHistoryTranslations: {
    es: string;
  };
  familyHistoryTranslations: {
    es: string;
  };
  medicationsTranslations: {
    es: string;
  };
  habitsTranslations: {
    es: string;
  };
  allergiesTranslations: {
    es: string;
  };
  concernsTranslations: {
    es: string;
  };
  physicalRequirementsTranslations: {
    es: string;
  };
  socioeconomicStatusTranslations: {
    es: string;
  };
  patientContextTranslations: {
    es: string;
  };
};

export type ClinicalCase = ClinicalCaseBase &
  PatientFields & {
    createdAt: string;
    updatedAt: string;
    organization: any | null;
  };

  export type ClinicalCaseWithTranslations = ClinicalCaseBase &
  PatientFields & TranslatedClinicalCase & {
    createdAt: string;
    updatedAt: string;
    organization: any | null;
  };