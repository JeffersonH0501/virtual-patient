import {useState} from 'react';
import {useTranslation} from 'react-i18next';
import {ArrowsClockwise, ComparisonIcon} from '../../icons';
import {EvaluationScore, Skeleton} from '../common';
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
  /** Whether the owner may regenerate the evaluation. Hides the button when false. */
  canRegenerate?: boolean;
  /** Whether a regeneration is currently running. Disables the button and shows skeletons. */
  isRegenerating?: boolean;
  /** Called when the owner clicks the regenerate button. */
  onRegenerate?: () => void;
};

const SKELETON_CRITERION_COUNT = 6;

export const EvaluationResultsPanel = ({
  evaluationData,
  className = '',
  canRegenerate = false,
  isRegenerating = false,
  onRegenerate,
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
        className={`flex h-full min-h-0 min-w-0 flex-col overflow-hidden rounded-card bg-white shadow-card ${className}`}
        aria-label={t('evaluation.interviewEvaluationResults')}
      >
        <header className="flex min-h-12 shrink-0 items-center justify-between gap-3 border-b border-slate-200 px-4">
          <h2 className="component-title text-left">
            {t('evaluation.interviewEvaluationResults')}
          </h2>
          {canRegenerate && (
            <button
              type="button"
              onClick={onRegenerate}
              disabled={isRegenerating}
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-control border-0 bg-slate-100 text-slate-700 transition-colors hover:bg-blue-50 hover:text-blue-700 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:bg-slate-100 disabled:hover:text-slate-700 [&_svg]:h-5 [&_svg]:w-5"
              title={t('evaluation.regenerateEvaluation')}
              aria-label={t('evaluation.regenerateEvaluation')}
            >
              <ArrowsClockwise color="currentColor" />
            </button>
          )}
        </header>
        {isRegenerating ? (
          <div
            className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 scrollbar-hidden"
            aria-hidden="true"
          >
            <div className="grid grid-cols-1 rounded-xl bg-gradient-to-r from-blue-50 to-indigo-50 p-4 sm:grid-cols-2 sm:items-stretch">
              <div className="space-y-3 border-b border-blue-100 pb-4 sm:border-b-0 sm:border-r sm:pb-0 sm:pr-4">
                <Skeleton className="h-4 w-40" />
                <Skeleton className="h-4 w-48" />
                <Skeleton className="h-4 w-32" />
              </div>
              <div className="flex flex-col items-center justify-center gap-3 pt-4 sm:pt-0 sm:pl-4">
                <Skeleton className="h-4 w-32" />
                <Skeleton className="h-16 w-16 rounded-full" />
                <Skeleton className="h-6 w-24 rounded-full" />
              </div>
            </div>
            <div className="space-y-3">
              {Array.from({length: SKELETON_CRITERION_COUNT}).map((_, index) => (
                <div
                  key={index}
                  className="rounded-panel border border-slate-200 bg-white p-4 shadow-card"
                >
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <Skeleton className="h-5 w-40" />
                    <Skeleton className="h-6 w-10 rounded-full" />
                  </div>
                  <Skeleton className="h-4 w-full" />
                  <Skeleton className="mt-2 h-4 w-5/6" />
                </div>
              ))}
            </div>
          </div>
        ) : (
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 scrollbar-hidden">
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
              <h3 className="component-subtitle">
                {t('evaluation.overallPerformance')}
              </h3>
              <EvaluationScore score={averageScore} size="large" className="mt-2" />
              <span className={`mt-2 inline-flex rounded-full px-3 py-1 text-xs font-medium ${getScoreColor(averageScore)}`}>
                {getScoreLabel(averageScore, t)}
              </span>
            </div>
          </div>

          <div className="space-y-3">
            {sortedResults.map((result) => (
              <article
                key={result.aspect}
                className="rounded-panel border border-slate-200 bg-white p-4 text-left shadow-card"
              >
                <div className="mb-3 flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-1">
                    <h4
                      role="button"
                      tabIndex={0}
                      aria-expanded={hoveredAspect === result.aspect}
                      onClick={() => setHoveredAspect(
                        hoveredAspect === result.aspect ? null : result.aspect,
                      )}
                      onKeyDown={(event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault();
                          setHoveredAspect(hoveredAspect === result.aspect ? null : result.aspect);
                        }
                      }}
                      className="component-subtitle cursor-pointer underline decoration-current underline-offset-2 transition-colors hover:text-blue-700 focus-visible:rounded-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-300"
                    >
                      {getAspectDisplayName(result.aspect, t)}
                    </h4>
                    <EvaluationCriteriaTooltip
                      aspect={result.aspect}
                      isVisible={hoveredAspect === result.aspect}
                      onClose={() => setHoveredAspect(null)}
                    />
                    {result.aspect === 'completeness' &&
                      (user?.role === 'teacher' || user?.role === 'superuser') && (
                        <button
                          type="button"
                          onClick={() => setIsComparisonOpen(true)}
                          className="p-1 text-blue-600 hover:text-blue-800 [&_svg]:h-6 [&_svg]:w-6"
                          title={t('evaluation.clinicalCaseComparison')}
                        >
                          <ComparisonIcon />
                        </button>
                      )}
                  </div>
                  <EvaluationScore score={result.score} size="small" className="shrink-0" />
                </div>
                <p className="text-sm leading-6 text-slate-600">
                  {result.feedback}
                </p>
              </article>
            ))}
          </div>
        </div>
        )}
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
