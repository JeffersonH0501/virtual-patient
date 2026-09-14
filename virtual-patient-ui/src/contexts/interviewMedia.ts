import {createContext, useContext} from 'react';

export type MediaAccessState = 'idle' | 'loading' | 'ready' | 'permission-denied' | 'unavailable' | 'unsupported';

export type InterviewMediaContextValue = {
  cameraStream: MediaStream | null;
  microphoneStream: MediaStream | null;
  cameraState: MediaAccessState;
  microphoneState: MediaAccessState;
  startCamera: () => Promise<void>;
  startMicrophone: () => Promise<void>;
  stopAll: () => void;
};

export const InterviewMediaContext = createContext<InterviewMediaContextValue | null>(null);

export const useInterviewMedia = (): InterviewMediaContextValue => {
  const context = useContext(InterviewMediaContext);
  if (!context) throw new Error('useInterviewMedia must be used inside InterviewMediaProvider');
  return context;
};
