export type Symptom = {
  symptom: string;
  status?: string | null;
  severity?: string | null;
  onset?: string | null;
  location?: string | null;
  triggers?: string | null;
};

export type Illness = {
  illness: string;
  status?: string | null;
  diagnosisDate?: string | null;
  severity?: string | null;
  treatment?: string | null;
  notes?: string | null;
};

export type Medication = {
  medication: string;
  duration?: string | null;
  frequency?: string | null;
  dosage?: string | null;
  purpose?: string | null;
};

export type FamilyHistory = {
  relationship: string;
  condition: string;
  notes?: string | null;
};

export type Habit = {
  habit: string;
  duration?: string | null;
  frequency?: string | null;
};

export type MedicalHistory = {
  type: string;
  date?: string | null;
  description?: string | null;
  outcome?: string | null;
};

export type CreateSummaryResponse = {
  summary_result: ProgressSummary | null;
};

export type ProgressSummary = {
  id?: number;
  medicalInterviewId?: number;
  age?: number | null;
  weightInKg?: number | null;
  currentSymptoms?: Symptom[];
  allergies?: string[] | null;
  medications?: Medication[] | null;
  currentIllnesses?: Illness[];
  familyHistory?: FamilyHistory[] | null;
  dietInformation?: string | null;
  habits?: Habit[] | null;
  workInformation?: string | null;
  medicalHistory?: MedicalHistory[] | null;
  summaryText?: string;
  updateCount?: number;
  lastUpdatedMessageId?: string;
  confidenceScore?: number;
  createdAt?: string;
  updatedAt?: string;
};
