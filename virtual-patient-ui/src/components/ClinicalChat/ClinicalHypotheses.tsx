import {FC, FormEvent, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {useParams} from 'react-router-dom';
import {createHypothesis} from '../../services/hypotheses';
import {completeInterview} from '../../services/interviews';
import {CreateHypothesisRequest} from '../../types/hypothesis';
import {InterviewEvaluationResponse} from '../../types/evaluation';

type ClinicalHypothesesProps = {
  onCancel: () => void;
  beforeComplete?: () => Promise<void>;
  onHypothesesSubmitted: (
    evaluationData: InterviewEvaluationResponse,
  ) => void | Promise<void>;
};

export const ClinicalHypotheses: FC<ClinicalHypothesesProps> = ({
  onCancel,
  beforeComplete,
  onHypothesesSubmitted,
}) => {
  const {t} = useTranslation();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [hypotheses, setHypotheses] = useState({
    hypothesis1: '',
    hypothesis2: '',
    hypothesis3: '',
  });
  const {interviewId: interviewIdParam} = useParams<{interviewId: string}>();
  const interviewId = interviewIdParam ? parseInt(interviewIdParam, 10) : null;

  const handleHypothesisChange = (field: keyof typeof hypotheses, value: string) => {
    setHypotheses((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    void submitHypotheses();
  };

  const submitHypotheses = async () => {
    if (!interviewId) {
      console.error('No interview ID found');
      return;
    }

    setIsSubmitting(true);
    try {
      const hypothesesToSubmit: CreateHypothesisRequest = [];

      if (hypotheses.hypothesis1.trim()) {
        hypothesesToSubmit.push({
          hypothesisText: hypotheses.hypothesis1.trim(),
          hypothesisOrder: 1,
        });
      }

      if (hypotheses.hypothesis2.trim()) {
        hypothesesToSubmit.push({
          hypothesisText: hypotheses.hypothesis2.trim(),
          hypothesisOrder: 2,
        });
      }

      if (hypotheses.hypothesis3.trim()) {
        hypothesesToSubmit.push({
          hypothesisText: hypotheses.hypothesis3.trim(),
          hypothesisOrder: 3,
        });
      }

      if (hypothesesToSubmit.length === 0) {
        console.error('No hypotheses to submit');
        return;
      }

      await createHypothesis(interviewId.toString(), hypothesesToSubmit);

      await beforeComplete?.();

      const evaluationData = await completeInterview(interviewId.toString());

      await onHypothesesSubmitted(evaluationData);
    } catch (error) {
      console.error('Failed to submit hypotheses:', error);
    } finally {
      setIsSubmitting(false);
    }
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
        <h2 className="dialog-title">
          {t('clinicalChat.clinicalHypotheses')}
        </h2>
      </header>

      <div className="flex-1 overflow-y-auto bg-surface p-4 sm:p-5">
        <p className="dialog-copy mb-4">
          {t('clinicalChat.hypothesesDescription')}
        </p>
        <div className="grid gap-3">
          {hypothesisFields.map((field) => (
            <div key={field.key}>
              <textarea
                id={field.key}
                aria-label={field.placeholder}
                value={hypotheses[field.key]}
                onChange={(event) => handleHypothesisChange(field.key, event.target.value)}
                placeholder={field.placeholder}
                rows={4}
                disabled={isSubmitting}
                className="w-full resize-none rounded-control border border-border bg-surface px-3 py-2.5 text-sm leading-5 text-slate-700 placeholder:text-slate-400 hover:border-neutral-400 disabled:cursor-not-allowed disabled:bg-neutral-100"
              />
            </div>
          ))}
        </div>
      </div>

      <footer className="flex shrink-0 justify-end bg-surface px-5 py-3.5">
        <div className="dialog-actions">
          <button
            type="button"
            onClick={onCancel}
            disabled={isSubmitting}
            className="dialog-action dialog-action--secondary"
          >
            {t('common.cancel')}
          </button>
          <button
            type="submit"
            disabled={!hasHypothesis || isSubmitting}
            className="dialog-action dialog-action--primary"
          >
            {isSubmitting ? t('common.loading') : t('clinicalChat.submit')}
          </button>
        </div>
      </footer>
    </form>
  );
};

