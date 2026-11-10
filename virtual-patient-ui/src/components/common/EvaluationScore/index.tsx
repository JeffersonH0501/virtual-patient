import {useTranslation} from 'react-i18next';
import {
  EVALUATION_SCORE_MAX,
  formatEvaluationScoreValue,
  getEvaluationScoreBand,
} from '../../../utils/evaluationScore';

type EvaluationScoreSize = 'compact' | 'large';

type EvaluationScoreProps = {
  score: number;
  size?: EvaluationScoreSize;
  className?: string;
};

export const EvaluationScore = ({score, size = 'compact', className = ''}: EvaluationScoreProps) => {
  const band = getEvaluationScoreBand(score);
  const {i18n} = useTranslation();
  const formattedScore = formatEvaluationScoreValue(score, i18n?.resolvedLanguage ?? i18n?.language);

  return (
    <span
      className={`evaluation-score evaluation-score--${band} ${className}`}
      aria-label={`${formattedScore}/${EVALUATION_SCORE_MAX}`}
    >
      <span className={`evaluation-score-value ${size === 'large' ? 'metric-value' : 'numeric-value'}`} aria-hidden="true">
        {formattedScore}
      </span>
      <span className="evaluation-score-scale" aria-hidden="true">
        / {EVALUATION_SCORE_MAX}
      </span>
    </span>
  );
};
