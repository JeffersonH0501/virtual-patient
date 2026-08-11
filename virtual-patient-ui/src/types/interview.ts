import {Message} from './message';
import {ProgressSummary} from './progress';
import {InterviewEvaluation} from './evaluation';
import {Personality} from './personality';
import { ClinicalCaseWithTranslations, ClinicalCase } from './clinicalCase';
import { SessionNote } from './sessionNote';
import { TeacherFeedback } from './teacherFeedback';

export type Status = 'active' | 'completed' | 'abandoned';

export type CompleteInterviewResponse = {
  id: number;
  userId: number;
  clinicalCaseId: number;
  status: Status;
  startTime: string;
  endTime: string;
  totalDuration: number | null;
  interviewMetadata: Record<string, any>;
  createdAt: string;
  clinicalCase: ClinicalCaseWithTranslations;
  messages: Message[];
  hypotheses?: Array<{
    id: number;
    interviewId: number;
    hypothesisText: string;
    hypothesisOrder: number;
  }>;
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
  status: Status;
  createdAt: string;
  endTime: string;
  startTime: string;
  clinicalCase: ClinicalCase;
  totalDuration: number;
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
  totalDuration: number;
  evaluationScore: number;
  organizationId: number;
  clinicalCaseTitle: string;
  userUsername: string;
  startTime: string;
  endTime: string;
  teacherFeedback: TeacherFeedback[];
  personality?: Personality | null;
};


