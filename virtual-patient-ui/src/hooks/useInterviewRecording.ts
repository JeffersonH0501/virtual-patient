import type {MediaAccessState} from '../contexts/interviewMedia';

export type UseInterviewRecordingOptions = {
  missingMessageIds?: number[];
  interviewId?: number;
  enabled: boolean;
  cameraStream: MediaStream | null;
  microphoneStream: MediaStream | null;
  microphoneState: MediaAccessState;
  cameraEnabled: boolean;
  microphoneEnabled: boolean;
  patientAudioEnabled: boolean;
  patientAvatar: string;
  patientName: string;
  resumeAttemptId?: string | null;
  initialOffsetMs?: number;
};

export {useBlockInterviewRecording as useInterviewRecording} from './useBlockInterviewRecording';
