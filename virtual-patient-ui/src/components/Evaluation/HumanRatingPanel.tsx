import {useEffect, useRef, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {gradingRequest, Workspace} from '../../services/teacherGrading';
import {Button, Field} from '../common';
import {Badge} from '../common/Badge';
import {MotionHeight} from '../common/Motion';
import {List} from 'lucide-react';
import {CompleteInterviewResponse} from '../../types/interview';
import {EvaluationResultsPanel} from './EvaluationResultsPanel';
import {getAspectDisplayName} from './helpers';
import {CaseDetailsDialog} from '../ClinicalCases/CaseDetailsDialog';
import {SubmittedHypothesesDialog} from './SubmittedHypothesesDialog';

export const HumanRatingPanel = ({
  assignmentId,
  selfInterviewId,
  onSubmitted,
  interview,
  aspectToEdit: submittedAspect,
  onCancel,
  onBusyChange,
  open = true,
}: {
  assignmentId?: number;
  selfInterviewId?: number;
  interview?: CompleteInterviewResponse;
  aspectToEdit?: string;
  onCancel?: () => void;
  onBusyChange?: (busy: boolean) => void;
  open?: boolean;
  onSubmitted: () => void | Promise<void>;
}) => {
  const {t} = useTranslation();
  const workspacePath = selfInterviewId === undefined ? '/teacher-assignments/' + assignmentId
    : '/medical-interviews/' + selfInterviewId + '/self-rating';
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [values, setValues] = useState<Record<string, {score: string; feedback: string}>>({});
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [draftAspect, setDraftAspect] = useState<string>();
  const [caseDetailsOpen, setCaseDetailsOpen] = useState(false);
  const [hypothesesOpen, setHypothesesOpen] = useState(false);
  const reviewInterviewId = interview?.id ?? selfInterviewId ?? workspace?.interviewId;
  const aspectToEdit = submittedAspect ?? draftAspect;
  const sending = useRef(false);
  const editorView = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (aspectToEdit) editorView.current?.focus({preventScroll: true});
  }, [aspectToEdit]);
  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const item = await gradingRequest<Workspace>(workspacePath);
      setWorkspace(item);
      setValues(
        Object.fromEntries(
          Object.keys(item.rubric).map((aspect) => {
            const result = item.results.find((entry) => entry.aspect === aspect);
            return [
              aspect,
              {
                score: result?.score == null ? '' : String(result.score),
                feedback: result?.feedback ?? '',
              },
            ];
          }),
        ),
      );
    } catch {
      setError(t('errors.generic'));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => {
    if (!open) return;
    setWorkspace(null);
    setValues({});
    setError('');
    void load();
  }, [workspacePath, open]);
  const act = async (operation: 'start' | 'draft' | 'submit') => {
    if (sending.current || (operation === 'submit' && !valid)) return;
    sending.current = true;
    setBusy(true);
    onBusyChange?.(true);
    setError('');
    setNotice('');
    try {
      const results = Object.entries(values).map(([aspect, value]) => ({
        aspect,
        score: value.score === '' ? null : Number(value.score),
        feedback: value.feedback.trim(),
      }));
      const item = await gradingRequest<Workspace>(
        workspacePath + '/' + operation,
        operation === 'draft' ? 'PUT' : 'POST',
        operation === 'start' ? undefined : {results},
      );
      setWorkspace(item);
      if (operation === 'submit') {
        await onSubmitted();
        setNotice(t('grading.ratingSaved'));
      } else if (operation === 'draft') {
        setDraftAspect(undefined);
      }
      return true;
    } catch {
      setError(t('grading.saveFailed'));
    } finally {
      sending.current = false;
      setBusy(false);
      onBusyChange?.(false);
    }
  };
  const isValidRating = (value?: {score: string; feedback: string}) =>
    Boolean(
      value &&
      value.score.trim() !== '' &&
      Number.isFinite(Number(value.score)) &&
      Number(value.score) >= 0 &&
      Number(value.score) <= 5 &&
      value.feedback.trim() !== '',
    );
  const valid =
    workspace &&
    Object.keys(workspace.rubric).length === 6 &&
    Object.values(values).length === 6 &&
    Object.values(values).every(isValidRating);
  const editedRating = aspectToEdit ? values[aspectToEdit] : undefined;
  const savedRating = workspace?.results.find((result) => result.aspect === aspectToEdit);
  const hasRatingChanges = editedRating && (
    (editedRating.score === '' ? null : Number(editedRating.score)) !== (savedRating?.score ?? null) ||
    editedRating.feedback.trim() !== (savedRating?.feedback ?? '').trim()
  );
  const ratingContent = (
    <>
      {error && (
        <p className="ui-notice ui-notice--danger" role="alert">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {!workspace && loading ? (
        <p role="status">{t('common.loading')}</p>
      ) : !workspace ? (
        <Button variant="secondary" disabled={busy} onClick={() => void load()}>
          {t('common.retry')}
        </Button>
      ) : workspace.status === 'pending' ? (
        <Button disabled={busy} onClick={() => void act('start')}>
          {t('grading.start')}
        </Button>
      ) : (
        <>
          {Object.entries(workspace.rubric)
            .filter(([aspect]) => !aspectToEdit || aspect === aspectToEdit)
            .map(([aspect, criteria]) => (
              <section
                className={aspectToEdit ? 'rating-component-editor' : 'space-y-layout'}
                key={aspect}
              >
                <header className="ui-text-pair">
                  <h3 className="default-title">{getAspectDisplayName(aspect, t)}</h3>
                </header>
                <section className="rating-component-criteria" aria-label={t('evaluation.evaluationCriteria')}>
                  <header className="rating-criteria-title">
                    <List aria-hidden="true" />
                    <span>{t('evaluation.evaluationCriteria')}</span>
                    <Badge tone="neutral">
                      {t('grading.criteriaCount', {count: criteria.length})}
                    </Badge>
                  </header>
                  {aspect === 'completeness' && reviewInterviewId !== undefined && (
                    <div className="mx-inset mt-inset flex flex-col items-start gap-layout">
                      <button type="button" className="ui-action-text underline secondary-text" onClick={() => setCaseDetailsOpen(true)}>{t('grading.viewFullClinicalCase')}</button>
                      <button type="button" className="ui-action-text underline secondary-text" onClick={() => setHypothesesOpen(true)}>{t('grading.viewSubmittedHypotheses')}</button>
                    </div>
                  )}
                  <ol className="rating-criteria-list secondary-text">
                    {criteria.map((criterion) => (
                      <li key={criterion}>
                        <span>{criterion}</span>
                      </li>
                    ))}
                  </ol>
                </section>

                <div className={aspectToEdit ? 'rating-editor-fields' : 'ui-form-stack'}>
                  {aspectToEdit ? (
                    <div className="ui-field">
                      <label htmlFor={'rating-' + aspect} className="ui-field-label text-neutral-500">
                        {t('evaluation.score')}
                      </label>
                      <div className="rating-score-control">
                        <div className="ui-input-wrapper">
                          <input
                            id={'rating-' + aspect}
                            type="number"
                            inputMode="decimal"
                            min={0}
                            max={5}
                            step="any"
                            required
                            disabled={busy}
                            value={values[aspect]?.score ?? ''}
                            onChange={(event) => {
                              const score = event.currentTarget.value;
                              setValues((current) => ({
                                ...current,
                                [aspect]: {...current[aspect], score},
                              }));
                            }}
                          />
                          <span className="shrink-0 pr-layout text-content-muted default-text" aria-hidden="true">
                            / 5
                          </span>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <Field
                      id={'rating-' + aspect}
                      type="number"
                      min={0}
                      max={5}
                      step="any"
                      label={t('grading.score')}
                      value={values[aspect]?.score ?? ''}
                      disabled={busy}
                      required
                      onChange={(event) =>
                        setValues((current) => ({
                          ...current,
                          [aspect]: {...current[aspect], score: event.target.value},
                        }))
                      }
                    />
                  )}
                  <div className="ui-field">
                    <label htmlFor={'feedback-' + aspect} className={aspectToEdit ? 'text-neutral-500' : undefined}>{t('grading.comment')}</label>
                    <textarea
                      id={'feedback-' + aspect}
                      className="ui-textarea"
                      rows={aspectToEdit ? 1 : undefined}
                      value={values[aspect]?.feedback ?? ''}
                      disabled={busy}
                      required
                      onChange={(event) => {
                        const feedback = event.currentTarget.value;
                        setValues((current) => ({
                          ...current,
                          [aspect]: {...current[aspect], feedback},
                        }));
                      }}
                    />
                  </div>
                </div>
              </section>
            ))}
          {!aspectToEdit && (
            <div className="ui-button-group flex flex-wrap">
              {workspace.status !== 'submitted' && (
                <Button variant="secondary" disabled={busy} onClick={() => void act('draft')}>
                  {t('grading.saveDraft')}
                </Button>
              )}
              <Button
                disabled={busy || !valid}
                onClick={() => void act('submit')}
              >
                {t(workspace.status === 'submitted' ? 'common.save' : 'grading.submit')}
              </Button>
            </div>
          )}
        </>
      )}
    </>
  );
  const editor = aspectToEdit && (
        <div
          ref={editorView}
          tabIndex={-1}
          className="rating-component-view"
          role="region"
          aria-label={t('grading.editScore')}
          aria-busy={busy}
        >
          {ratingContent}
          <div className="ui-button-group ui-button-group--large justify-center mt-inset">
            <Button variant="secondary" disabled={busy} onClick={submittedAspect ? onCancel : () => {
              const saved = workspace?.results.find((result) => result.aspect === draftAspect);
              setValues((current) => ({
                ...current,
                [aspectToEdit]: {score: saved?.score == null ? '' : String(saved.score), feedback: saved?.feedback ?? ''},
              }));
              setDraftAspect(undefined);
            }}>
              {t('common.cancel')}
            </Button>
            <Button
              disabled={busy || !hasRatingChanges || (submittedAspect ? !valid : !isValidRating(editedRating))}
              onClick={() => void act(submittedAspect ? 'submit' : 'draft')}
            >
              {t('common.save')}
            </Button>
          </div>
        </div>
  );
  return (
    <>
      {caseDetailsOpen && reviewInterviewId !== undefined && (
        <CaseDetailsDialog interviewId={reviewInterviewId} onClose={() => setCaseDetailsOpen(false)} />
      )}
      {hypothesesOpen && reviewInterviewId !== undefined && <SubmittedHypothesesDialog interviewId={reviewInterviewId} onClose={() => setHypothesesOpen(false)} />}
      {interview ? (
        <EvaluationResultsPanel
          className="xl:col-start-3 xl:row-start-1"
          evaluationData={{interview, evaluationResults: []}}
          hideConditionSelector
          assessmentControls={workspace?.status !== 'submitted' ? <div className="assessment-controls"><p className="ui-notice text-left">{t('grading.completeBeforeAutomaticEvaluation')}</p></div> : undefined}
          draftResults={Object.keys(workspace?.rubric ?? {}).map((aspect) => ({
            aspect,
            score: values[aspect]?.score ? Number(values[aspect].score) : null,
            feedback: values[aspect]?.feedback ?? '',
          }))}
          isLoading={loading && !workspace}
          pendingMessage={loading ? t('common.loading') : t('errors.generic')}
          onEditScore={async (aspect) => {
            if (sending.current) return;
            if (workspace?.status === 'pending' && !(await act('start'))) return;
            setDraftAspect(aspect);
          }}
          editorContent={editor || undefined}
          tableFooter={
            <>
              {error && <p className="ui-notice ui-notice--danger" role="alert">{error}</p>}
              {notice && <p role="status">{notice}</p>}
              {!workspace && !loading && (
                <Button variant="secondary" onClick={() => void load()}>{t('common.retry')}</Button>
              )}
              {workspace?.status === 'in_progress' && (
                <div className="ui-button-group ui-button-group--large mt-inset justify-center">
                  <Button disabled={busy || !valid} onClick={() => void act('submit')}>
                    {t('grading.submit')}
                  </Button>
                </div>
              )}
            </>
          }
        />
      ) : editor || (
        <section className="ui-panel flex min-h-0 flex-col overflow-hidden xl:col-start-3 xl:row-start-1">
          <header className="ui-panel-header">
          <h2 className="default-title">{t('evaluation.interviewEvaluationResults')}</h2>
          </header>
          <div className="ui-panel-body overflow-y-auto">
            {workspace?.status !== 'submitted' && <p className="ui-notice">{t('grading.completeBeforeAutomaticEvaluation')}</p>}
            <MotionHeight fade={false} className="space-y-layout">{ratingContent}</MotionHeight>
          </div>
        </section>
      )}
    </>
  );
};
