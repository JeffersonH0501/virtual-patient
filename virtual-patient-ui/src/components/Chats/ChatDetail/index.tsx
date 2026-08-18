import {NotesCard} from './NotesCard';
import {HypothesesCard} from './HypothesesCard';
import {ChatInterface} from './ChatInterface';
import {AnalysisSidebar} from './AnalysisSidebar';
import {PatientProfile} from '../../ClinicalChat/PatientProfile';
import {HYPOTHESES, MESSAGES} from '../../ClinicalChat/mock';
import {Patient} from '../../../types';
import {useState} from 'react';
import patientImageM from '../../../assets/patient_m.png';

export const ChatDetail = () => {
  const [hypotheses] = useState<string[]>(HYPOTHESES);

  const initialPatient: Patient = {
    name: '',
    id: '',
    avatar: patientImageM,
    online: true,
    basicInfo: {
      age: 0,
      gender: '',
      bloodType: '',
      weight: '',
    },
    symptoms: [],
    allergies: [],
    diet: '',
    illnesses: [],
    medications: [],
    summary: '',
  };

  return (
    <main className="flex gap-8 p-4 min-h-screen bg-gray-100 max-md:flex-col max-sm:p-4 justify-center w-full">
      <aside className="flex flex-col gap-8 w-80 max-md:w-full">
        <PatientProfile patient={initialPatient} />
        <NotesCard />
        <HypothesesCard hypotheses={hypotheses} />
      </aside>
      <ChatInterface durationInSeconds={1380} messages={MESSAGES} />
      <AnalysisSidebar />
    </main>
  );
};
