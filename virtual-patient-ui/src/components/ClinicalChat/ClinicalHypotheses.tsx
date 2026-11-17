import {DialogShell} from '../common/Dialog';
import {CSSProperties, FC, FormEvent, useRef, useState} from 'react';
import {FormInput} from '../common/FormInput';
import {useTranslation} from 'react-i18next';
import {LoaderCircle} from 'lucide-react';
import {useParams} from 'react-router-dom';
import {createHypothesis} from '../../services/hypotheses';
import {completeInterview} from '../../services/interviews';
import {CreateHypothesisRequest} from '../../types/hypothesis';
import {InterviewEvaluationResponse} from '../../types/evaluation';

type SubmissionPhase = 'editing' | 'saving' | 'error';

// Share of the bar for each saving stage: hypotheses, then the recording (uploads and verification), then completion.
const HYPOTHESES_END = 10;
const RECORDING_END = 90;

type ClinicalHypothesesProps = {
  onCancel: () => void;
  canCancel?: boolean;
  preparingCapture?: boolean;
  captureSegmentId?: string | null;
  recordingError?: string;
  beforeComplete?: (onProgress: (fraction: number) => void) => Promise<boolean>;
  waitingForTurn?: boolean;
} & (
  | {onCompleted: (evaluationData: InterviewEvaluationResponse) => void | Promise<void>; onDemoSubmit?: never}
  | {onDemoSubmit: () => void; onCompleted?: never}
);

export const ClinicalHypotheses: FC<ClinicalHypothesesProps> = ({
  onCancel,
  canCancel = true,
  preparingCapture = false,
  captureSegmentId,
  recordingError,
  beforeComplete,
  waitingForTurn = false,
  onCompleted,
  onDemoSubmit,
}) => {
  const {t} = useTranslation();
  const [phase, setPhase] = useState<SubmissionPhase>('editing');
  const [percent, setPercent] = useState(0);
  const submittingRef = useRef(false);
  const hypothesesSavedRef = useRef(false);
  const [hypotheses, setHypotheses] = useState({hypothesis1: '', hypothesis2: '', hypothesis3: ''});
  const {interviewId: interviewIdParam} = useParams<{interviewId: string}>();
  const interviewId = interviewIdParam ? parseInt(interviewIdParam, 10) : null;

  const handleHypothesisChange = (field: keyof typeof hypotheses, value: string) => {
    setHypotheses((previous) => ({...previous, [field]: value}));
  };

  const hypothesesToSubmit = (): CreateHypothesisRequest => {
    const values = [hypotheses.hypothesis1, hypotheses.hypothesis2, hypotheses.hypothesis3];
    return values.flatMap((value, index) => {
      const hypothesisText = value.trim();
      return hypothesisText ? [{hypothesisText, hypothesisOrder: index + 1}] : [];
    });
  };

  const submitHypotheses = async () => {
    if (submittingRef.current || waitingForTurn || preparingCapture) return;
    const request = hypothesesToSubmit();
    if (request.length === 0) return;
    if (onDemoSubmit) {
      onDemoSubmit();
      return;
    }
    if (!interviewId || !onCompleted) return;
    submittingRef.current = true;
    setPhase('saving');
    // The bar never goes backwards, even when a retry repeats a stage that was already counted.
    const advance = (next: number) => setPercent((current) => Math.max(current, Math.min(100, Math.round(next))));
    advance(0);
    try {
      if (!hypothesesSavedRef.current) {
        await createHypothesis(interviewId.toString(), request, captureSegmentId);
        hypothesesSavedRef.current = true;
      }
      advance(HYPOTHESES_END);
      const recordingSaved = await beforeComplete?.(
        (fraction) => advance(HYPOTHESES_END + fraction * (RECORDING_END - HYPOTHESES_END)));
      if (recordingSaved === false) throw new Error('Interview recording was not saved');
      advance(RECORDING_END);
      const nextEvaluationData = await completeInterview(interviewId.toString(), 'user_completed', captureSegmentId);
      advance(100);
      await onCompleted(nextEvaluationData);
    } catch (error) {
      console.error('Failed to finish interview:', error);
      setPhase('error');
    } finally {
      submittingRef.current = false;
    }
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    void submitHypotheses();
  };
  const hasHypothesis = Object.values(hypotheses).some((value) => value.trim());
  const cancel = () => {
    if (canCancel && !submittingRef.current) onCancel();
  };
  const busy = phase === 'saving';
  const hypothesisFields = [
    {key: 'hypothesis1', placeholder: t('clinicalChat.enterHypothesis1')},
    {key: 'hypothesis2', placeholder: t('clinicalChat.enterHypothesis2')},
    {key: 'hypothesis3', placeholder: t('clinicalChat.enterHypothesis3')},
  ] as const;

  return (
    <DialogShell
      title={t('clinicalChat.clinicalHypotheses')}
      onClose={cancel}
      busy={busy}
      onSubmit={handleSubmit}
      hasDismissAction
      actions={
        <>
          <button
            type="button"
            onClick={cancel}
            disabled={!canCancel || busy}
            className="ui-button ui-button--secondary"
          >
            {t('common.cancel')}
          </button>
          <button
            type="submit"
            disabled={!hasHypothesis || busy || preparingCapture || waitingForTurn}
            className="ui-button ui-button--primary"
          >
            {phase === 'error'
              ? t('common.retry')
              : phase === 'saving'
                ? t('clinicalChat.saving')
                : t('clinicalChat.submit')}
          </button>
        </>
      }
    >
      <p className="dialog-copy mb-layout">{t('clinicalChat.hypothesesDescription')}</p>
      <div className="grid gap-layout pb-[calc(var(--focus-outline-width)+var(--focus-outline-offset))]">
        {hypothesisFields.map((field) => (
          <FormInput
            label=""
            type="textarea"
            key={field.key}
            id={field.key}
            aria-label={field.placeholder}
            value={hypotheses[field.key]}
            onChange={(event) => handleHypothesisChange(field.key, event.target.value)}
            placeholder={field.placeholder}
            rows={2}
            resizable
            disabled={hypothesesSavedRef.current || busy}
          />
        ))}
      </div>
      {phase === 'saving' && (
        <div
          className="ui-notice mt-layout flex items-center gap-layout text-left"
          role="status"
          aria-live="polite"
        >
          <LoaderCircle className="h-4 w-4 shrink-0 motion-safe:animate-spin" />
          <div className="min-w-0 flex-1 space-y-[var(--layout-gap-small)]">
            <span>{t('clinicalChat.finalization.savingDescription')} {t('clinicalChat.finalization.savingPercent', {percent})}</span>
            <div
              role="progressbar"
              aria-label={t('clinicalChat.finalization.savingTitle')}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={percent}
              className="h-2 w-full overflow-hidden rounded-full bg-neutral-200"
            >
              <div
                className="progress-fill h-full rounded-full bg-brand-600 transition-[width] duration-300 motion-reduce:transition-none"
                style={{'--progress-width': `${percent}%`} as CSSProperties}
              />
            </div>
          </div>
        </div>
      )}
      {phase === 'error' && (
        <div
          className="ui-notice ui-notice--danger mt-layout text-left"
          role="alert"
        >
          <p>{t('clinicalChat.finalization.errorDescription')}</p>
        </div>
      )}
      {recordingError && <p role="alert" className="mt-layout text-danger-700 default-text">{recordingError}</p>}
    </DialogShell>
  );
};
