import { EvaluationResult } from '../../../types/evaluation';
import {getEvaluationScoreBand} from '../../../utils/evaluationScore';

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
  const band = getEvaluationScoreBand(score);
  if (band === 'high') return 'bg-success-50 text-success-700';
  if (band === 'medium') return 'bg-warning-50 text-warning-700';
  return 'bg-danger-50 text-danger-700';
};

export const getScoreLabel = (score: number, t: any): string => {
  const band = getEvaluationScoreBand(score);
  if (band === 'high') return t('evaluation.excellent');
  if (band === 'medium') return t('evaluation.fair');
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
