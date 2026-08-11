import { Message } from '../../../types/message';
import { Patient } from '../../../types/patient';
import { ProgressSummary, Symptom } from '../../../types/progress';
import patientImageM from '../../../assets/patient_m.png';
import patientImageF from '../../../assets/patient_f.png';
import doctorImage from '../../../assets/doctor.png';

// Helper function to get appropriate patient image based on gender
export const getPatientImage = (gender?: string) => {
  if (gender?.toLowerCase() === 'female' || gender?.toLowerCase() === 'f') {
    return patientImageF;
  }
  return patientImageM; // Default to male or when gender is not specified
};

// Helper function to process messages with proper avatars
export const processMessagesWithAvatars = (messages: Message[], patientGender?: string | null) => {
  return messages.map((message: Message) => {
    if (
      (message.senderType === 'patient' || message.senderType === 'chatbot') &&
      !message.senderAvatar
    ) {
      return {
        ...message,
        senderAvatar: getPatientImage(patientGender || undefined),
      };
    }
    if (message.senderType === 'user' && !message.senderAvatar) {
      return {
        ...message,
        senderAvatar: doctorImage,
      };
    }
    return message;
  });
};

export const processSummaryData = (progressSummary: ProgressSummary) => {
  return (prevPatient: Patient) => {
    const updatedPatient = {...prevPatient};

    // Update age if provided and not null
    if (progressSummary.age !== undefined && progressSummary.age !== null) {
      updatedPatient.basicInfo = {
        ...updatedPatient.basicInfo,
        age: progressSummary.age,
      };
    }

    // Update symptoms only if provided in API response
    if (progressSummary.currentSymptoms && progressSummary.currentSymptoms.length > 0) {
      updatedPatient.symptoms = progressSummary.currentSymptoms.map((symptom: Symptom) => ({
        text: symptom.symptom,
        variant: 'blue' as const,
      }));
    }

    // Update allergies only if provided in API response
    if (progressSummary.allergies && progressSummary.allergies.length > 0) {
      updatedPatient.allergies = progressSummary.allergies.map((allergy: string) => ({
        text: allergy,
        variant: 'red' as const,
      }));
    }

    if (progressSummary.dietInformation && progressSummary.dietInformation !== null) {
      updatedPatient.diet = progressSummary.dietInformation;
    }

    if (progressSummary.currentIllnesses && progressSummary.currentIllnesses.length > 0) {
      updatedPatient.illnesses = progressSummary.currentIllnesses;
    }

    if (progressSummary.medications && progressSummary.medications.length > 0) {
      updatedPatient.medications = progressSummary.medications;
    }

    if (progressSummary.familyHistory && progressSummary.familyHistory.length > 0) {
      updatedPatient.familyHistory = progressSummary.familyHistory;
    }

    if (progressSummary.habits && progressSummary.habits.length > 0) {
      updatedPatient.habits = progressSummary.habits;
    }

    if (progressSummary.workInformation && progressSummary.workInformation !== null) {
      updatedPatient.workInformation = progressSummary.workInformation;
    }

    if (progressSummary.medicalHistory && progressSummary.medicalHistory.length > 0) {
      updatedPatient.medicalHistory = progressSummary.medicalHistory;
    }

    if (progressSummary.summaryText) {
      updatedPatient.summary = progressSummary.summaryText;
    }

    return updatedPatient;
  };
};
