import {Badge} from '../common/Badge';
import {CSSProperties, ReactNode, useEffect, useId, useRef, useState} from 'react';
import {createPortal} from 'react-dom';
import {RecapTurn} from '../../types/recording';
import {useTranslation} from 'react-i18next';
import {ChevronDown, CircleQuestionMark, Pencil, RefreshCw} from 'lucide-react';
import {Button, ConfirmationModal, EvaluationScore, Modal} from '../common';
import {useUser} from '../../hooks/useUser';
import {EvaluationCondition, InterviewEvaluationResponse} from '../../types/evaluation';
import {ClinicalCaseComparison} from './ClinicalCaseComparison';
import {EvaluationCriteriaTooltip} from './EvaluationCriteriaTooltip';
import {requestLearningMoments} from '../../services/evaluations/learningMoments';
import {LearningMoment} from '../../types/learningMoments';
import {getAspectDisplayName, getScoreTone, getScoreLabel, sortEvaluationResults} from './helpers';
import {TableHeader} from '../common/Table/TableHeader';
import {readDesignNumber} from '../../utils/designTokens';
import {MotionContent, MotionHeight} from '../common/Motion';
import {useAppMotion, usePresence} from '../common/Motion/hooks';
import {Dialog} from '../common/Dialog';

type EvaluationResultsPanelProps = {
  evaluationData: InterviewEvaluationResponse;
  className?: string;
  humanLabel?: string;
  assessmentKey?: string;
  selectedCondition?: EvaluationCondition;
  hideConditionSelector?: boolean;
  assessmentControls?: ReactNode;
  headerAction?: ReactNode;
  onEditScore?: (aspect: string) => void;
  editorContent?: ReactNode;
  draftResults?: {aspect: string; score: number | null; feedback: string}[];
  tableFooter?: ReactNode;
  pendingMessage?: string;
  isLoading?: boolean;
  /** Whether the superuser may regenerate the evaluation. Hides the button when false. */
  canRegenerate?: boolean;
  /** Whether regeneration is running; keep confirmed results visible while controls are disabled. */
  isRegenerating?: boolean;
  /** Called when the superuser clicks the regenerate button. */
  onRegenerate?: () => void;
  onReprocess?: () => void;
  isReprocessing?: boolean;
  refreshDisabled?: boolean;
  evaluationStale?: boolean;
  turns?: RecapTurn[];
  onJumpToTurn?: (turnId: string) => void;
};

export const EvaluationResultsPanel = ({
  evaluationData,
  className = '',
  humanLabel,
  assessmentKey,
  selectedCondition,
  hideConditionSelector = false,
  assessmentControls,
  headerAction,
  onEditScore,
  editorContent,
  draftResults,
  tableFooter,
  pendingMessage,
  isLoading = false,
  canRegenerate: regenerationAllowed = false,
  isRegenerating = false,
  onRegenerate,
  onReprocess,
  isReprocessing = false,
  refreshDisabled = false,
  evaluationStale = false,
  turns = [],
  onJumpToTurn,
}: EvaluationResultsPanelProps) => {
  const {t} = useTranslation();
  const {user} = useUser();
  const canRegenerate = regenerationAllowed && user?.role === 'superuser';
  const refreshActionLabel = t(onReprocess ? 'evaluation.refreshActions' : 'evaluation.regenerateEvaluation');
  const panelElement = useRef<HTMLElement>(null);
  const editingFocus = useRef<string | null>(null);
  const editComponent = (aspect: string) => {
    editingFocus.current = aspect;
    onEditScore?.(aspect);
  };
  useEffect(() => {
    if (editorContent != null || !editingFocus.current) return;
    const trigger = Array.from(
      panelElement.current?.querySelectorAll<HTMLButtonElement>('[data-edit-aspect]') ?? [],
    ).find((button) => button.dataset.editAspect === editingFocus.current);
    trigger?.focus();
    editingFocus.current = null;
  }, [editorContent]);
  const {interview, evaluationResults} = evaluationData;
  const canOpenComparison = draftResults
    ? Boolean(interview.clinicalCase || interview.hypotheses?.length)
    : interview.reviewAccess?.canViewAssessments !== false
      && Boolean(interview.hypotheses?.length || (interview.clinicalCase && interview.progressSummary));
  const [localCondition, setLocalCondition] = useState<EvaluationCondition>('TEXT_ONLY');
  const condition = selectedCondition ?? localCondition;
  const [criteriaAspect, setCriteriaAspect] = useState<string | null>(null);
  const evaluationKey = assessmentKey ?? humanLabel ?? condition;
  const [expandedFor, setExpandedFor] = useState(evaluationKey);
  const [expandedAspects, setExpandedAspects] = useState<Set<string>>(new Set());
  if (expandedFor !== evaluationKey) {
    setExpandedFor(evaluationKey);
    setExpandedAspects(new Set());
  }
  const [learningMoments, setLearningMoments] = useState<LearningMoment[]>([]);
  const feedbackId = useId();
  const staleTooltipId = useId();
  const regenerateControl = useRef<HTMLSpanElement>(null);
  const [tooltipHovered, setTooltipHovered] = useState(false);
  const [tooltipFocused, setTooltipFocused] = useState(false);
  const [tooltipPosition, setTooltipPosition] = useState<CSSProperties>({});
  const showStaleTooltip = canRegenerate && evaluationStale && (tooltipHovered || tooltipFocused);
  const {enabled: motionEnabled} = useAppMotion();
  const stalePresence = usePresence(showStaleTooltip);
  const positionStaleTooltip = () => {
    const rect = regenerateControl.current?.querySelector('button')?.getBoundingClientRect();
    if (!rect) return;
    const inset = readDesignNumber('--layout-inset');
    const width = Math.min(
      readDesignNumber('--evaluation-tooltip-width'),
      window.innerWidth - inset * 2,
    );
    setTooltipPosition({
      left: Math.max(inset, Math.min(rect.right - width, window.innerWidth - width - inset)),
      top: rect.bottom + readDesignNumber('--layout-gap-small'),
      width,
    });
  };
  useEffect(() => {
    if (!showStaleTooltip) return;
    window.addEventListener('resize', positionStaleTooltip);
    window.addEventListener('scroll', positionStaleTooltip, true);
    return () => {
      window.removeEventListener('resize', positionStaleTooltip);
      window.removeEventListener('scroll', positionStaleTooltip, true);
    };
  }, [showStaleTooltip]);
  // Confirmation applies only to evaluation of already saved observations.
  const [isRegenerateConfirmOpen, setIsRegenerateConfirmOpen] = useState(false);
  useEffect(() => {
    setCriteriaAspect(null);
    setIsRegenerateConfirmOpen(false);
  }, [evaluationKey]);

  const confirmRegenerate = () => {
    setIsRegenerateConfirmOpen(false);
    if (canRegenerate && !isRegenerating && !refreshDisabled) onRegenerate?.();
  };
  const toggleFeedback = (aspect: string) =>
    setExpandedAspects((previous) => {
      const next = new Set(previous);
      if (next.has(aspect)) next.delete(aspect);
      else next.add(aspect);
      return next;
    });
  const sortedResults = draftResults
    ? sortEvaluationResults(draftResults)
    : condition === 'TEXT_ONLY'
      ? sortEvaluationResults(evaluationResults)
      : sortEvaluationResults(evaluationData.multimodalEvaluationResults ?? []);
  const overallScore =
    condition === 'TEXT_ONLY'
      ? interview.interviewEvaluation?.overallScore
      : interview.multimodalInterviewEvaluation?.overallScore;
  const isPending = isLoading || isRegenerating;
  const showLearningMoments = condition === 'TEXT_PLUS_MULTIMODAL' && !draftResults && !humanLabel
    && editorContent == null && sortedResults.length > 0 && !isPending && !refreshDisabled;
  const sourceRevision = interview.multimodalInterviewEvaluation?.updatedAt;
  useEffect(() => {
    setLearningMoments([]);
    if (!showLearningMoments) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const result = await requestLearningMoments(interview.id);
        if (disposed) return;
        if (result.status === 'pending' || result.status === 'processing') {
          timer = setTimeout(() => void load(), 2000);
        } else if (result.status === 'completed' && !result.stale) {
          setLearningMoments(result.moments.slice(0, 3));
        }
      } catch {
        // The category feedback remains available if its supplemental moments cannot load.
      }
    }
    void load();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [interview.id, sourceRevision, showLearningMoments]);
  const hasOverallScore = sortedResults.length > 0 && typeof overallScore === 'number';
  const tableHeader = (
    <TableHeader
      columns={[t('evaluation.component'), t('evaluation.score'), t('conversations.action')]}
      hideLastLabel
    />
  );

  return (
    <>
      <section
        ref={panelElement}
        className={`ui-panel flex h-full min-h-0 min-w-0 flex-col overflow-hidden ${className}`}
        aria-label={humanLabel ?? t('evaluation.interviewEvaluationResults')}
        aria-busy={isPending}
      >
        <header className="ui-panel-header ui-panel-header--title-sized shrink-0">
          <h2 className="text-left default-title">{t('evaluation.interviewEvaluationResults')}</h2>
          {(canRegenerate || headerAction) && (
            <div className="ml-auto flex items-center gap-layout">
              {canRegenerate && (
                <span
                  ref={regenerateControl}
                  className="evaluation-regenerate-control panel-header-action"
                  onMouseEnter={() => {
                    positionStaleTooltip();
                    setTooltipHovered(true);
                  }}
                  onMouseLeave={() => setTooltipHovered(false)}
                  onFocus={() => {
                    positionStaleTooltip();
                    setTooltipFocused(true);
                  }}
                  onBlur={() => setTooltipFocused(false)}
                  onKeyDown={(event) => {
                    if (event.key === 'Escape') {
                      setTooltipHovered(false);
                      setTooltipFocused(false);
                    }
                  }}
                >
                  <button
                    type="button"
                    onClick={() => {
                      setTooltipHovered(false);
                      setTooltipFocused(false);
                      setIsRegenerateConfirmOpen(true);
                    }}
                    disabled={isRegenerating || refreshDisabled}
                    aria-busy={isRegenerating || isReprocessing || undefined}
                    className={`ui-icon-button${evaluationStale ? ' ui-icon-button--warning' : ''}`}
                    title={evaluationStale ? undefined : refreshActionLabel}
                    aria-label={refreshActionLabel}
                    aria-describedby={showStaleTooltip ? staleTooltipId : undefined}
                  >
                    <RefreshCw className={isRegenerating || isReprocessing ? 'motion-safe:animate-spin' : undefined} />
                    {evaluationStale && (
                      <span className="evaluation-regenerate-dot" aria-hidden="true" />
                    )}
                  </button>
                </span>
              )}
              {headerAction}
            </div>
          )}
        </header>
        {stalePresence.present &&
          createPortal(
            <div
              id={staleTooltipId}
              role="tooltip"
              aria-hidden={!showStaleTooltip || undefined}
              data-ui-motion={motionEnabled ? 'app' : undefined}
              data-motion-state={stalePresence.state}
              onAnimationEnd={stalePresence.onAnimationEnd}
              className="evaluation-regenerate-tooltip motion-tooltip"
              style={tooltipPosition}
            >
              {t('evaluation.stale')}
            </div>,
            document.body,
          )}
        {assessmentControls}
        {!humanLabel && !hideConditionSelector && (
          <div
            className="evaluation-condition-selector"
            role="group"
            aria-label={t('evaluation.condition')}
          >
            {(['TEXT_ONLY', 'TEXT_PLUS_MULTIMODAL'] as const).map((option) => (
              <Button
                key={option}
                variant={condition === option ? 'primary' : 'secondary'}
                aria-pressed={condition === option}
                onClick={() => {
                  setLocalCondition(option);
                  setCriteriaAspect(null);
                }}
              >
                {t(
                  option === 'TEXT_ONLY'
                    ? 'evaluation.originalCondition'
                    : 'evaluation.multimodalCondition',
                )}
              </Button>
            ))}
          </div>
        )}
        <div className="ui-panel-body min-h-0 flex-1 overflow-y-auto scrollbar-hidden">
          <MotionContent
            changeKey={editorContent != null ? 'component-editor' : 'results'}
            slide
          >
            {editorContent == null &&
              !draftResults &&
              !isPending &&
              hasOverallScore && (
                <div className="flex justify-center rounded-t-xl bg-brand-50 ui-panel-body">
                    <div className="flex flex-col items-center gap-[var(--layout-gap-small)] text-center">
                      <h3 className="default-title">{t('evaluation.overallScore')}</h3>
                      <EvaluationScore score={overallScore} size="large" />
                      <Badge tone={getScoreTone(overallScore)}>{getScoreLabel(overallScore, t)}</Badge>
                    </div>
                </div>
              )}
            {editorContent != null ? (
              editorContent
            ) : isPending && sortedResults.length === 0 ? (
              <p role="status" className="ui-panel-body">{t('common.loading')}</p>
            ) : (
              <div>
                {sortedResults.length === 0 && (
                  <p className="text-content-muted default-text">
                    {pendingMessage ?? t('evaluation.multimodalUnavailable')}
                  </p>
                )}

                {sortedResults.length > 0 && (
                  <div className="ui-table-scroll" tabIndex={0}>
                    <table
                      className="ui-data-table evaluation-criteria-table"
                      aria-label={t('evaluation.criteriaTable')}
                    >
                      {tableHeader}
                      {sortedResults.map((result) => {
                        const label = getAspectDisplayName(result.aspect, t);
                        const moments = showLearningMoments
                          ? learningMoments.filter((moment) => moment.category === result.aspect)
                          : [];
                        const canExpand = !draftResults || result.score != null;
                        const expanded = canExpand && expandedAspects.has(result.aspect);
                        const detailsId = feedbackId + '-' + result.aspect;
                        return (
                          <tbody
                            key={result.aspect}
                            className="evaluation-criterion-group"
                            data-expanded={expanded}
                          >
                            <tr
                              className="evaluation-component-row"
                              onClick={(event) => {
                                if (
                                  !canExpand || (event.target as Element).closest(
                                    'button, a, input, select, textarea, [role="button"]',
                                  )
                                ) {
                                  return;
                                }
                                toggleFeedback(result.aspect);
                              }}
                            >
                              <th scope="row">
                                <div className="flex min-w-0 items-center gap-layout">
                                  <span>{label}</span>
                                  {!onEditScore && (
                                    <>
                                      <button
                                        type="button"
                                        className="ui-icon-button ui-icon-button--plain"
                                        aria-haspopup="dialog"
                                        aria-expanded={criteriaAspect === result.aspect}
                                        aria-label={t('evaluation.viewCriteriaFor', {
                                          component: label,
                                        })}
                                        onClick={() => setCriteriaAspect(result.aspect)}
                                      >
                                        <CircleQuestionMark aria-hidden="true" />
                                      </button>
                                      <EvaluationCriteriaTooltip
                                        aspect={result.aspect}
                                        condition={condition}
                                        isVisible={criteriaAspect === result.aspect}
                                        onClose={() => setCriteriaAspect(null)}
                                        comparison={result.aspect === 'completeness' && canOpenComparison ? (
                                          <ClinicalCaseComparison
                                            clinicalCase={interview.clinicalCase}
                                            progressSummary={interview.progressSummary}
                                            hypotheses={interview.hypotheses}
                                          />
                                        ) : undefined}
                                      />
                                    </>
                                  )}
                                </div>
                              </th>
                              <td>
                                <div className="flex items-center gap-[var(--layout-gap-small)]">
                                  {result.score != null && (
                                    <EvaluationScore score={result.score} size="compact" />
                                  )}
                                  {onEditScore && (
                                    <Button
                                      variant="secondary"
                                      className="ui-icon-button"
                                      aria-label={t('grading.editScore')}
                                      title={t('grading.editScore')}
                                      data-edit-aspect={result.aspect}
                                      onClick={() => editComponent(result.aspect)}
                                    >
                                      <Pencil aria-hidden="true" />
                                    </Button>
                                  )}
                                </div>
                              </td>
                              <td>
                                {canExpand && <button
                                  type="button"
                                  className="evaluation-feedback-toggle"
                                  aria-expanded={expanded}
                                  aria-controls={detailsId}
                                  aria-label={t('evaluation.toggleFeedback', {criterion: label})}
                                  onClick={() => toggleFeedback(result.aspect)}
                                >
                                  <ChevronDown
                                    className={
                                      expanded ? 'motion-chevron rotate-180' : 'motion-chevron'
                                    }
                                  />
                                </button>}
                              </td>
                            </tr>
                            <tr
                              className={
                                expanded
                                  ? 'evaluation-feedback-row'
                                  : 'evaluation-feedback-row motion-feedback-row-closed'
                              }
                              aria-hidden={!expanded || undefined}
                            >
                              <td colSpan={3}>
                                <MotionHeight key={evaluationKey} expanded={expanded}>
                                  <div
                                    id={detailsId}
                                    role="region"
                                    className="motion-feedback space-y-layout"
                                    aria-label={t('evaluation.feedbackForCriterion', {
                                      criterion: label,
                                    })}
                                  >
                                    <p className="text-content-muted default-text">
                                      {result.feedback || (draftResults && '—')}
                                    </p>
                                    {moments.length > 0 && (
                                      <section className="space-y-layout" aria-label={t('learningMoments.title')}>
                                        <h4 className="default-title">{t('learningMoments.title')}</h4>
                                        {moments.map((moment) => (
                                          <article key={moment.id} className={`space-y-layout ui-notice ${moment.type === 'strength' ? 'ui-notice--success' : 'ui-notice--warning'}`}>
                                            <p>{moment.observation} {moment.recommendation}</p>
                                            <div className="ui-button-group" aria-label={t('learningMoments.linkedTurns')}>
                                              {turns.map((turn, index) => moment.turnIds.includes(turn.turnId) && (
                                                <Button key={turn.turnId} variant="secondary" className="ui-button--brand-soft" disabled={!onJumpToTurn} onClick={() => onJumpToTurn?.(turn.turnId)}>
                                                  {t('evaluation.turnReference', {id: index + 1})}
                                                </Button>
                                              ))}
                                            </div>
                                          </article>
                                        ))}
                                      </section>
                                    )}
                                  </div>
                                </MotionHeight>
                              </td>
                            </tr>
                          </tbody>
                        );
                      })}
                    </table>
                  </div>
                )}
                {tableFooter}
              </div>
            )}
          </MotionContent>
        </div>
      </section>

      {onReprocess ? (
        <Dialog
          open={isRegenerateConfirmOpen && canRegenerate && !isRegenerating && !refreshDisabled}
          title={refreshActionLabel}
          onClose={() => setIsRegenerateConfirmOpen(false)}
        >
          <div className="flex flex-col items-start gap-layout">
            {onRegenerate && (
              <>
                <p>{t('evaluation.regenerateEvaluationWarning')}</p>
                <Button onClick={confirmRegenerate}>{t('evaluation.regenerateEvaluation')}</Button>
              </>
            )}
            <p>{t('clinicalChat.recap.refreshAnalysisWarning')}</p>
            <Button onClick={() => {
              setIsRegenerateConfirmOpen(false);
              if (canRegenerate && !isRegenerating && !refreshDisabled) onReprocess();
            }}>{t('clinicalChat.recap.refreshAnalysis')}</Button>
          </div>
        </Dialog>
      ) : <Modal
        open={isRegenerateConfirmOpen && canRegenerate && !isRegenerating && !refreshDisabled}
        ariaLabel={t('evaluation.regenerateEvaluation')}
        closeAction={() => setIsRegenerateConfirmOpen(false)}
      >
        <ConfirmationModal
          title={t('evaluation.regenerateEvaluation')}
          description={t('evaluation.regenerateEvaluationWarning')}
          cancelLabel={t('common.cancel')}
          confirmLabel={t('common.accept')}
          confirmVariant="primary"
          onCancel={() => setIsRegenerateConfirmOpen(false)}
          onConfirm={confirmRegenerate}
        />
      </Modal>}
    </>
  );
};
