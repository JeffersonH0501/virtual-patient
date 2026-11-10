export type LearningMoment = {
  id: string;
  category: 'show_interest' | 'show_empathy' | 'speak_clearly';
  type: 'strength' | 'improvement';
  turnIds: string[];
  observation: string;
  recommendation: string;
  evidenceUsed: string[];
};

export type LearningMomentsState = {
  status: 'not_generated' | 'pending' | 'processing' | 'completed' | 'failed';
  stale: boolean;
  moments: LearningMoment[];
};
