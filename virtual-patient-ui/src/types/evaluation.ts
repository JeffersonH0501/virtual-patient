import {CompleteInterviewResponse} from './interview';

export type EvaluationResult = {
  aspect: 'completeness' | 'show_interest' | 'show_empathy' | 'speak_clearly' | 'open_communication' | 'general_communication';
  score: number;
  feedback: string;
  timestamp: string;
};

export type EvaluationCondition = 'TEXT_ONLY' | 'TEXT_PLUS_MULTIMODAL';

export type CriticalTurn = {turnId: string; annotation: string};

export type MultimodalEvaluationResult = EvaluationResult & {
  /** Historical read compatibility only; new scoring does not generate these. */
  criticalTurns?: CriticalTurn[];
};

export type MultimodalAspectMetadata = {
  aspect: string;
  criteria: string[];
  nonverbalFamilies: string[];
  paraverbalFamilies: string[];
  evidence: string[];
  multimodalEvaluationAspects?: string[];
  observationNote: string;
};

export type InterviewEvaluationResponse = {
  interview: CompleteInterviewResponse;
  evaluationResults: EvaluationResult[];
  multimodalEvaluationResults?: MultimodalEvaluationResult[];
};

export type InterviewEvaluation = {
  id: number;
  medicalInterviewId: number;
  evaluationResults: EvaluationResult[];
  overallScore: number;
  completionTimestamp: string;
  createdAt: string;
  updatedAt: string;
  evaluationCondition?: EvaluationCondition;
};

export type MultimodalInterviewEvaluation = Omit<InterviewEvaluation, 'evaluationResults' | 'overallScore'> & {
  evaluationResults: MultimodalEvaluationResult[];
  overallScore: number | null;
};
