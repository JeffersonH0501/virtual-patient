import { Illness, Medication, FamilyHistory, Habit, MedicalHistory } from './progress';

export type Tag = {
  text: string;
  variant: 'blue' | 'red';
};

export type Patient = {
  name: string;
  id: string;
  avatar: string;
  online: boolean;
  basicInfo: {
    age: number;
    gender: string;
    bloodType: string;
    weight?: string;
  };
  symptoms: Tag[];
  allergies: Tag[];
  diet: string;
  illnesses?: Illness[];
  medications?: Medication[];
  familyHistory?: FamilyHistory[];
  habits?: Habit[];
  workInformation?: string;
  medicalHistory?: MedicalHistory[];
  summary?: string;
};
