import type {MediaAccessState} from '../contexts/interviewMedia';

export type UseInterviewRecordingOptions = {
  missingMessageIds?: number[];
  studentMessageIds?: number[];
  patientMessageIds?: number[];
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
  recoveredPatientMessageId?: number | null;
  initialPatientMessageId?: number | null;
  initialOffsetMs?: number;
};

export {useTurnInterviewRecording as useInterviewRecording} from './useTurnInterviewRecording';
