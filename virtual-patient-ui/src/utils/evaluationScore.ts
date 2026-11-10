export const EVALUATION_SCORE_MIN = 0;
export const EVALUATION_SCORE_MAX = 5;
export const EVALUATION_SCORE_PASSING_MIN = 3;
export const EVALUATION_SCORE_HIGH_MIN = 4;

export type EvaluationScoreBand = 'low' | 'medium' | 'high';

export const getEvaluationScoreBand = (score: number): EvaluationScoreBand => {
  if (score >= EVALUATION_SCORE_HIGH_MIN) return 'high';
  if (score >= EVALUATION_SCORE_PASSING_MIN) return 'medium';
  return 'low';
};

export const formatEvaluationScoreValue = (score: number, language = 'en'): string => {
  const rounded = score.toFixed(1);
  return language.startsWith('es') ? rounded.replace('.', ',') : rounded;
};
