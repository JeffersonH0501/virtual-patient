export type LearningMoment = {
  id: string;
  category: 'show_interest' | 'show_empathy' | 'speak_clearly';
  turnIds: string[];
  observation: string;
  recommendation?: string;
  reinforcement?: string;
  evidenceUsed: string[];
  momentType: 'improvement' | 'strength';
};

export type LearningMomentsState = {
  status: 'not_generated' | 'pending' | 'processing' | 'completed' | 'failed';
  stale: boolean;
  moments: LearningMoment[];
  providerProvenance?: {aspect: string; promptMessages?: {role: string; content: unknown}[]}[];
};
