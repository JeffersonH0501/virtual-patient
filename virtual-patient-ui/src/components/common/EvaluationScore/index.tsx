import {
  EVALUATION_SCORE_MAX,
  formatEvaluationScoreValue,
  getEvaluationScoreBand,
} from '../../../utils/evaluationScore';

type EvaluationScoreSize = 'small' | 'medium' | 'large';

type EvaluationScoreProps = {
  score: number;
  size?: EvaluationScoreSize;
  className?: string;
};

export const EvaluationScore = ({score, size = 'medium', className = ''}: EvaluationScoreProps) => {
  const band = getEvaluationScoreBand(score);
  const sizeClass = size === 'medium' ? 'regular' : size;
  const formattedScore = formatEvaluationScoreValue(score);

  return (
    <span
      className={`evaluation-score evaluation-score--${band} evaluation-score--${sizeClass} ${className}`}
      aria-label={`${formattedScore}/${EVALUATION_SCORE_MAX}`}
    >
      <span className="evaluation-score-value" aria-hidden="true">
        {formattedScore}
      </span>
      <span className="evaluation-score-scale" aria-hidden="true">
        / {EVALUATION_SCORE_MAX}
      </span>
    </span>
  );
};
