import {Message} from './message';
import {ProgressSummary} from './progress';
import {InterviewEvaluation} from './evaluation';
import {Personality} from './personality';
import { ClinicalCaseWithTranslations, ClinicalCase } from './clinicalCase';
import { SessionNote } from './sessionNote';
import { TeacherFeedback } from './teacherFeedback';

export type Status = 'in_progress' | 'processing' | 'completed' | 'interrupted';

export type CalibrationInputLevel = 'low' | 'adequate' | 'high';

// Per-participant numeric reference derived from calibration media by the
// backend `POST /calibration/baseline` endpoint (camelCased from the backend
// `PersonalBaseline` schema). Fundamental frequency is in semitones only, never
// Hertz. Both gaze axes are required; when any required metric is unavailable,
// the whole baseline is null and calibration is still allowed to be saved.
export type PersonalBaseline = {
  baselineF0Semitones: number;
  baselineLoudness: number;
  neutralHeadYaw: number;
  neutralHeadPitch: number;
  neutralHeadRoll: number;
  neutralGazeYaw: number;
  neutralGazePitch: number;
};

export type CalibrationResult = {
  version: 'technical_v2';
  status: 'passed' | 'failed';
  completedAt: string;
  durationMs: number;
  recordingSupported: boolean;
  audio: {
    microphoneAvailable: boolean;
    streamActive: boolean;
    voiceDetected: boolean;
    inputLevel: CalibrationInputLevel;
    clippingDetected: boolean;
  };
  video: {
    cameraAvailable: boolean;
    streamActive: boolean;
    faceDetected: boolean;
    faceDetectionRate: number;
    qualityStatus: 'adequate' | 'inadequate';
  };
  // Derived from the calibration media by the baseline endpoint. Null when
  // derivation was unavailable (or not attempted); calibration still saves.
  personalBaseline?: PersonalBaseline | null;
};

export type CompleteInterviewResponse = {
  id: number;
  publicId: string;
  userId: number;
  clinicalCaseId: number;
  status: Status;
  startTime: string | null;
  endTime: string | null;
  totalDuration: number | null;
  interviewMetadata: {
    patientResponseLanguage?: 'en' | 'es';
    calibration?: CalibrationResult;
    [key: string]: unknown;
  };
  createdAt: string;
  clinicalCase: ClinicalCaseWithTranslations;
  messages: Message[];
  hypotheses?: {
    id: number;
    interviewId: number;
    hypothesisText: string;
    hypothesisOrder: number;
  }[];
  sessionNotes: SessionNote[];
  progressSummary: ProgressSummary;
  interviewEvaluation?: InterviewEvaluation;
  patientName?: string | null;
  patientPhoto?: string | null;
  patientGender?: string | null;
  personality?: Personality | null;
  isOwner: boolean;
};

export type Interview = {
  id: string;
  publicId: string;
  status: Status;
  createdAt: string;
  endTime: string | null;
  startTime: string | null;
  clinicalCase: ClinicalCase;
  totalDuration: number | null;
};

export type InterviewListItem = Interview & {
  id: number;
  userId: number;
  clinicalCaseId: number;
  totalDuration: number | null;
  evaluationScore: number;
  personality?: Personality | null;
};

export type OrganizationInterview = {
  id: number;
  userId: number;
  clinicalCaseId: number;
  status: Status;
  totalDuration: number | null;
  evaluationScore: number;
  organizationId: number;
  clinicalCaseTitle: string;
  userName: string;
  startTime: string | null;
  endTime: string | null;
  teacherFeedback: TeacherFeedback[];
  personality?: Personality | null;
};
