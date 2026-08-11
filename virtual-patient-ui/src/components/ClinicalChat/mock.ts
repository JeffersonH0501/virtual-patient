import {Message} from '../../types/';
import patientImageM from '../../assets/patient_m.png';
import doctorImage from '../../assets/doctor.png';

export const MESSAGES: Message[] = [
  {
    id: 1,
    content:
      'I have been experiencing severe headaches for the past week, especially in the morning.',
    createdAt: new Date().toISOString(),
    senderType: 'patient',
    interviewId: 1,
    senderAvatar: patientImageM,
  },
  {
    id: 2,
    content:
      'Can you describe the location of your headaches? Are they concentrated in a specific area?',
    createdAt: new Date().toISOString(),
    senderType: 'user',
    interviewId: 1,
    senderAvatar: doctorImage,
  },
  {
    id: 3,
    content: '',
    createdAt: new Date().toISOString(),
    senderType: 'patient',
    interviewId: 1,
    senderAvatar: patientImageM,
  },
];

export const HYPOTHESES = [
  'Primary consideration based on symptom pattern and location, suggesting tension headaches with possible chronic development',
  'Secondary consideration due to recent onset and accompanying symptoms, indicating potential sinus-related headaches',
  'Tertiary consideration based on symptom duration and intensity, raising suspicion of possible migraines',
];
