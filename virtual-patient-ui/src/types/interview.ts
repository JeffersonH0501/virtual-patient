import {Message} from './message';
import {ProgressSummary} from './progress';
import {InterviewEvaluation} from './evaluation';
import {Personality} from './personality';
import { ClinicalCaseWithTranslations, ClinicalCase } from './clinicalCase';
import { SessionNote } from './sessionNote';
import { TeacherFeedback } from './teacherFeedback';

export type Status = 'in_progress' | 'processing' | 'completed' | 'interrupted';

// Per-participant numeric reference derived from the calibration media by the
// backend temporary-processing worker (camelCased from the backend
// `PersonalBaseline` schema). Fundamental frequency is in semitones only, never
// Hertz. Both gaze axes are required; a passed calibration always carries one.
export type PersonalBaseline = {
  baselineF0Semitones: number;
  baselineLoudness: number;
  neutralHeadYaw: number;
  neutralHeadPitch: number;
  neutralHeadRoll: number;
  neutralGazeYaw: number;
  neutralGazePitch: number;
};

// The calibration result persisted into an interview when it starts. It is the
// draft produced by `POST /calibration/process` plus a server completion time.
// A passed calibration carries the numeric personal baseline and the profile
// (including the gaze affine matrix) the multimodal pipeline consumes.
export type CalibrationResult = {
  version: string;
  status: 'passed' | 'failed';
  failureReason?: string | null;
  completedAt: string;
  profile?: Record<string, unknown> | null;
  quality?: Record<string, unknown> | null;
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
