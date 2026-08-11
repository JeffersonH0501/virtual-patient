export type UserHypothesisBase = {
  hypothesisText: string;
  hypothesisOrder: number; // 1-3
};

export type UserHypothesisUpdate = {
  hypothesisText?: string;
  hypothesisOrder?: number;
};

export type UserHypothesis = {
  id: number;
  medicalInterviewId: number;
  hypothesisText: string;
  hypothesisOrder: number;
};

export type CreateHypothesisRequest = UserHypothesisBase[];
