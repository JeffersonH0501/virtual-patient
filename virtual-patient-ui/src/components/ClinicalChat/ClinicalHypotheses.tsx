import {FC, FormEvent, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {useParams} from 'react-router-dom';
import {createHypothesis} from '../../services/hypotheses';
import {completeInterview} from '../../services/interviews';
import {CreateHypothesisRequest} from '../../types/hypothesis';
import {InterviewEvaluationResponse} from '../../types/evaluation';

type SubmissionPhase = 'editing' | 'saving' | 'error';

type ClinicalHypothesesProps = {
  onCancel: () => void;
  beforeComplete?: () => Promise<boolean>;
  onCompleted: (evaluationData: InterviewEvaluationResponse) => void | Promise<void>;
};

export const ClinicalHypotheses: FC<ClinicalHypothesesProps> = ({
  onCancel,
  beforeComplete,
  onCompleted,
}) => {
  const {t} = useTranslation();
  const [phase, setPhase] = useState<SubmissionPhase>('editing');
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
    if (!interviewId) return;
    const request = hypothesesToSubmit();
    if (request.length === 0) return;
    setPhase('saving');
    try {
      await createHypothesis(interviewId.toString(), request);
      const recordingSaved = await beforeComplete?.();
      if (recordingSaved === false) throw new Error('Interview recording was not saved');
      const nextEvaluationData = await completeInterview(interviewId.toString());
      await onCompleted(nextEvaluationData);
    } catch (error) {
      console.error('Failed to finish interview:', error);
      setPhase('error');
    }
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    void submitHypotheses();
  };
  const hasHypothesis = Object.values(hypotheses).some((value) => value.trim());
  const hypothesisFields = [
    {key: 'hypothesis1', placeholder: t('clinicalChat.enterHypothesis1')},
    {key: 'hypothesis2', placeholder: t('clinicalChat.enterHypothesis2')},
    {key: 'hypothesis3', placeholder: t('clinicalChat.enterHypothesis3')},
  ] as const;

  return (
    <form onSubmit={handleSubmit} className="flex max-h-dialog min-h-0 w-full flex-col overflow-hidden rounded-panel bg-surface text-left">
      <header className="shrink-0 border-b border-border bg-surface px-5 py-3.5">
        <h2 className="dialog-title">{t('clinicalChat.clinicalHypotheses')}</h2>
      </header>
      <div className="flex-1 overflow-y-auto bg-surface p-4 sm:p-5">
        <p className="dialog-copy mb-4">{t('clinicalChat.hypothesesDescription')}</p>
        <div className="grid gap-3">
          {hypothesisFields.map((field) => (
            <textarea
              key={field.key}
              id={field.key}
              aria-label={field.placeholder}
              value={hypotheses[field.key]}
              onChange={(event) => handleHypothesisChange(field.key, event.target.value)}
              placeholder={field.placeholder}
              rows={4}
              disabled={phase === 'saving'}
              className="w-full resize-none rounded-control border border-border bg-surface px-3 py-2.5 text-sm leading-5 text-slate-700 placeholder:text-slate-400 hover:border-neutral-400 disabled:cursor-not-allowed disabled:bg-neutral-100"
            />
          ))}
        </div>
        {phase === 'saving' && (
          <div className="mt-4 flex items-center gap-3 rounded-lg bg-blue-50 px-4 py-3 text-left text-sm text-blue-700" role="status" aria-live="polite">
            <span className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-blue-200 border-t-blue-600" aria-hidden="true" />
            <span>{t('clinicalChat.finalization.savingDescription')}</span>
          </div>
        )}
        {phase === 'error' && (
          <div className="mt-4 rounded-lg bg-red-50 px-4 py-3 text-left text-sm text-red-700" role="alert">
            {t('clinicalChat.finalization.errorDescription')}
          </div>
        )}
      </div>
      <footer className="flex shrink-0 justify-end bg-surface px-5 py-3.5">
        <div className="dialog-actions">
          <button type="button" onClick={onCancel} disabled={phase === 'saving'} className="dialog-action dialog-action--secondary">{t('common.cancel')}</button>
          <button type="submit" disabled={!hasHypothesis || phase === 'saving'} className="dialog-action dialog-action--primary">
            {phase === 'error' ? t('common.retry') : phase === 'saving' ? t('clinicalChat.saving') : t('clinicalChat.submit')}
          </button>
        </div>
      </footer>
    </form>
  );
};
