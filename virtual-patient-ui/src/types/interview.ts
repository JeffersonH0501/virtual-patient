import {Message} from './message';
import {ProgressSummary} from './progress';
import {InterviewEvaluation} from './evaluation';
import {Personality} from './personality';
import { ClinicalCaseWithTranslations, ClinicalCase } from './clinicalCase';
import { SessionNote } from './sessionNote';
import { TeacherFeedback } from './teacherFeedback';

export type Status = 'active' | 'completed' | 'abandoned';

export type CalibrationInputLevel = 'low' | 'adequate' | 'high';

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
  personalBaseline: null;
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
  userFirstName: string;
  userLastName: string;
  startTime: string | null;
  endTime: string | null;
  teacherFeedback: TeacherFeedback[];
  personality?: Personality | null;
};
