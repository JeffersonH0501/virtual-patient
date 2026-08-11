import { CompleteInterviewResponse } from "./interview";

export type EvaluationResult = {
  aspect: 'completeness' | 'show_interest' | 'show_empathy' | 'speak_clearly' | 'open_communication' | 'general_communication';
  score: number;
  feedback: string;
  timestamp: string;
};

export type InterviewEvaluationResponse = {
  interview: CompleteInterviewResponse;
  evaluationResults: EvaluationResult[];
};

export type InterviewEvaluation = {
  id: number;
  medicalInterviewId: number;
  evaluationResults: EvaluationResult[];
  overallScore: number;
  completionTimestamp: string;
  createdAt: string;
  updatedAt: string;
};
