import {useState} from 'react';
import {useTranslation} from 'react-i18next';
import {ComparisonIcon, StarIcon} from '../../icons';
import {useUser} from '../../hooks/useUser';
import {EvaluationResult, InterviewEvaluationResponse} from '../../types/evaluation';
import {ClinicalCaseComparisonModal} from './ClinicalCaseComparisonModal';
import {EvaluationCriteriaTooltip} from './EvaluationCriteriaTooltip';
import {
  calculateDuration,
  formatDateTime,
  formatDuration,
  getAspectDisplayName,
  getScoreColor,
  getScoreLabel,
  sortEvaluationResults,
} from './helpers';

type EvaluationResultsPanelProps = {
  evaluationData: InterviewEvaluationResponse;
  className?: string;
};

export const EvaluationResultsPanel = ({
  evaluationData,
  className = '',
}: EvaluationResultsPanelProps) => {
  const {t} = useTranslation();
  const {user} = useUser();
  const {interview, evaluationResults} = evaluationData;
  const [hoveredAspect, setHoveredAspect] = useState<EvaluationResult['aspect'] | null>(null);
  const [isComparisonOpen, setIsComparisonOpen] = useState(false);
  const sortedResults = sortEvaluationResults(evaluationResults);
  const averageScore = evaluationResults.length
    ? evaluationResults.reduce((sum, result) => sum + result.score, 0) /
      evaluationResults.length
    : 0;

  return (
    <>
      <section
        className={`flex h-full min-h-0 min-w-0 flex-col overflow-hidden rounded-xl bg-white shadow-[0_1px_2px_rgba(0,0,0,0.06)] ${className}`}
        aria-label={t('evaluation.interviewEvaluationResults')}
      >
        <header className="flex min-h-12 shrink-0 items-center border-b border-slate-200 px-4">
          <h2 className="text-left text-sm font-medium text-slate-600">
            {t('evaluation.interviewEvaluationResults')}
          </h2>
        </header>
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
          <div className="grid grid-cols-1 rounded-xl bg-gradient-to-r from-blue-50 to-indigo-50 p-4 sm:grid-cols-2 sm:items-stretch">
            <dl className="space-y-2 border-b border-blue-100 pb-4 text-left text-sm sm:border-b-0 sm:border-r sm:pb-0 sm:pr-4">
              <div>
                <dt className="text-xs text-slate-500">{t('evaluation.started')}</dt>
                <dd className="mt-0.5 text-slate-800">{formatDateTime(interview.startTime)}</dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500">{t('evaluation.completed')}</dt>
                <dd className="mt-0.5 text-slate-800">{formatDateTime(interview.endTime)}</dd>
              </div>
              <div>
                <dt className="text-xs text-slate-500">{t('evaluation.duration')}</dt>
                <dd className="mt-0.5 text-slate-800">
                  {formatDuration(
                    interview.totalDuration ||
                      calculateDuration(interview.startTime, interview.endTime),
                  )}
                </dd>
              </div>
            </dl>
            <div className="flex flex-col items-center justify-center pt-4 text-center sm:pt-0 sm:pl-4">
              <h3 className="text-sm font-medium text-slate-600">
                {t('evaluation.overallPerformance')}
              </h3>
              <div className="mt-2 flex items-baseline justify-center gap-1">
                <span className="text-3xl font-bold text-blue-600">{averageScore.toFixed(1)}</span>
                <span className="text-sm text-slate-500">/ 10</span>
              </div>
              <span className={`mt-2 inline-flex rounded-full px-3 py-1 text-xs font-medium ${getScoreColor(averageScore)}`}>
                {getScoreLabel(averageScore, t)}
              </span>
            </div>
          </div>

          <div className="space-y-3">
            {sortedResults.map((result) => (
              <article key={result.aspect} className="rounded-xl border border-slate-200 p-4 text-left">
                <div className="mb-2 flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-1">
                    <h4 className="text-sm font-medium text-slate-800">
                      {getAspectDisplayName(result.aspect, t)}
                    </h4>
                    <EvaluationCriteriaTooltip
                      aspect={result.aspect}
                      isVisible={hoveredAspect === result.aspect}
                      onMouseEnter={() => setHoveredAspect(result.aspect)}
                      onMouseLeave={() => setHoveredAspect(null)}
                    />
                    {result.aspect === 'completeness' &&
                      (user?.role === 'teacher' || user?.role === 'superuser') && (
                        <button
                          type="button"
                          onClick={() => setIsComparisonOpen(true)}
                          className="p-1 text-blue-600 hover:text-blue-800"
                          title={t('evaluation.clinicalCaseComparison')}
                        >
                          <ComparisonIcon size={18} />
                        </button>
                      )}
                  </div>
                  <span className={`shrink-0 rounded-full px-2 py-1 text-xs font-medium ${getScoreColor(result.score)}`}>
                    {result.score}/10
                  </span>
                </div>
                <div className="mb-2 flex gap-1" aria-hidden="true">
                  {[...Array(5)].map((_, index) => (
                    <span
                      key={index}
                      className={`h-4 w-4 ${
                        index < Math.floor(result.score / 2)
                          ? 'text-yellow-400'
                          : 'text-slate-300'
                      }`}
                    >
                      <StarIcon />
                    </span>
                  ))}
                </div>
                <p className="text-sm leading-5 text-slate-600">{result.feedback}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {interview.clinicalCase && interview.progressSummary && (
        <ClinicalCaseComparisonModal
          isOpen={isComparisonOpen}
          onClose={() => setIsComparisonOpen(false)}
          clinicalCase={interview.clinicalCase}
          progressSummary={interview.progressSummary}
          hypotheses={interview.hypotheses}
        />
      )}
    </>
  );
};
