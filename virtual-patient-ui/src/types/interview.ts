import {Message} from './message';
import {ProgressSummary} from './progress';
import {InterviewEvaluation, MultimodalInterviewEvaluation} from './evaluation';
import {Personality} from './personality';
import { ClinicalCaseWithTranslations, ClinicalCase } from './clinicalCase';
import { SessionNote } from './sessionNote';
import { TeacherFeedback } from './teacherFeedback';

export type Status = 'in_progress' | 'processing' | 'completed' | 'interrupted';

// Per-participant numeric reference derived from the calibration media by the
// backend temporary-processing worker (camelCased from the backend
// `PersonalBaseline` schema). Both gaze axes are required.
export type PersonalBaseline = {
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
  lifecycle?: {
    phase: 'preparing' | 'active' | 'resume_required' | 'capture_finalized' | 'processing' | 'completed' | 'interrupted' | 'completion_failed';
    canResumeCapture: boolean;
    canComplete: boolean;
    canRetryCompletion: boolean;
    errorCode?: string | null;
    recordingTransport?: string | null;
  } | null;
  reviewAccess?: {canViewAssessments: boolean; assignmentId: number | null; canAssignTeachers?: boolean; selfAssessmentRequired?: boolean};
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
    completionProcessing?: {status: 'queued' | 'failed' | 'complete'; errorCode?: string};
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
  multimodalInterviewEvaluation?: MultimodalInterviewEvaluation | null;
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
  isAssigned?: boolean;
  manualRatingStatus?: 'pending' | 'in_progress' | 'submitted';
  interviewMetadata?: CompleteInterviewResponse['interviewMetadata'];
  id: number;
  userId: number;
  clinicalCaseId: number;
  totalDuration: number | null;
  evaluationScore: number | null;
  personality?: Personality | null;
  analysisProgress?: {
    completed: number;
    total: number;
    percentage: number;
  } | null;
  reviewProgress?: number | null;
};

export type OrganizationInterview = {
  ownerRole?: 'student' | 'teacher' | 'superuser';
  createdAt: string;
  publicId: string;
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
  reviewProgress?: number | null;
  personality?: Personality | null;
};
