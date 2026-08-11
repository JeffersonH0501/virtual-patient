import { EvaluationResult } from '../../../types/evaluation';

export const getAspectDisplayName = (aspect: EvaluationResult['aspect'], t: any): string => {
  switch (aspect) {
    case 'general_communication':
      return t('evaluation.generalCommunication');
    case 'completeness':
      return t('evaluation.completeness');
    case 'show_interest':
      return t('evaluation.showingInterest');
    case 'show_empathy':
      return t('evaluation.showingEmpathy');
    case 'speak_clearly':
      return t('evaluation.speakingClearly');
    case 'open_communication':
      return t('evaluation.openCommunication');
    default:
      return aspect;
  }
};

export const getScoreColor = (score: number): string => {
  if (score >= 9) return 'text-green-600 bg-green-50';
  if (score >= 7) return 'text-blue-600 bg-blue-50';
  if (score >= 5) return 'text-yellow-600 bg-yellow-50';
  return 'text-red-600 bg-red-50';
};

export const getScoreLabel = (score: number, t: any): string => {
  if (score >= 9) return t('evaluation.excellent');
  if (score >= 7) return t('evaluation.good');
  if (score >= 5) return t('evaluation.fair');
  return t('evaluation.needsImprovement');
};

export const sortEvaluationResults = (results: EvaluationResult[]): EvaluationResult[] => {
  const order = ['general_communication', 'completeness', 'show_interest', 'show_empathy', 'speak_clearly', 'open_communication'];
  return [...results].sort((a, b) => {
    const aIndex = order.indexOf(a.aspect);
    const bIndex = order.indexOf(b.aspect);
    const aPos = aIndex === -1 ? order.length : aIndex;
    const bPos = bIndex === -1 ? order.length : bIndex;
    return aPos - bPos;
  });
};
