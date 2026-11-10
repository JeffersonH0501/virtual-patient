import type {BadgeTone} from '../../common/Badge';
import {getEvaluationScoreBand} from '../../../utils/evaluationScore';

export const getAspectDisplayName = (aspect: string, t: any): string => {
  switch (aspect) {
    case 'general_communication':
      return t('evaluation.generalCommunication');
    case 'completeness':
      return t('evaluation.completeness');
    case 'show_interest':
      return t('evaluation.interestInPatient');
    case 'show_empathy':
      return t('evaluation.understandingAndEmpathy');
    case 'speak_clearly':
      return t('evaluation.communicationClarity');
    case 'open_communication':
      return t('evaluation.openCommunication');
    default:
      return aspect;
  }
};

export const getScoreTone = (score: number): BadgeTone => {
  const band = getEvaluationScoreBand(score);
  if (band === 'high') return 'success';
  if (band === 'medium') return 'warning';
  return 'danger';
};

export const getScoreLabel = (score: number, t: any): string => {
  const band = getEvaluationScoreBand(score);
  if (band === 'high') return t('evaluation.excellent');
  if (band === 'medium') return t('evaluation.fair');
  return t('evaluation.needsImprovement');
};

export const EVALUATION_ASPECT_ORDER = ['general_communication', 'completeness', 'show_interest', 'show_empathy', 'speak_clearly', 'open_communication'];

export const sortEvaluationResults = <T extends {aspect: string}>(results: T[]): T[] => {
  return [...results].sort((a, b) => {
    const aIndex = EVALUATION_ASPECT_ORDER.indexOf(a.aspect);
    const bIndex = EVALUATION_ASPECT_ORDER.indexOf(b.aspect);
    const aPos = aIndex === -1 ? EVALUATION_ASPECT_ORDER.length : aIndex;
    const bPos = bIndex === -1 ? EVALUATION_ASPECT_ORDER.length : bIndex;
    return aPos - bPos;
  });
};
