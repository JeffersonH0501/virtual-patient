import {createContext, useContext} from 'react';

export type MediaAccessState = 'idle' | 'loading' | 'ready' | 'permission-denied' | 'unavailable' | 'unsupported';

export type InterviewMediaContextValue = {
  cameraStream: MediaStream | null;
  microphoneStream: MediaStream | null;
  cameraState: MediaAccessState;
  microphoneState: MediaAccessState;
  cameraDeviceId: string;
  microphoneDeviceId: string;
  startCamera: (deviceId?: string) => Promise<void>;
  startMicrophone: (deviceId?: string) => Promise<void>;
  stopAll: () => void;
  bindInterview: (interviewId: string) => void;
};

export const InterviewMediaContext = createContext<InterviewMediaContextValue | null>(null);

export const useInterviewMedia = (): InterviewMediaContextValue => {
  const context = useContext(InterviewMediaContext);
  if (!context) throw new Error('useInterviewMedia must be used inside InterviewMediaProvider');
  return context;
};
