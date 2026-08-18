import {FC, FormEvent, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {FormInput} from '../common/';
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

  return (
    <form onSubmit={handleSubmit} className="flex w-full flex-col gap-4 p-5 sm:p-6">
      <header className="border-b border-slate-200 pb-3 text-left">
        <h2 className="text-lg font-semibold text-slate-800">
          {t('clinicalChat.clinicalHypotheses')}
        </h2>
      </header>
        <FormInput
          label={t('clinicalChat.hypothesis1')}
          value={hypotheses.hypothesis1}
          onChange={(e) => handleHypothesisChange('hypothesis1', e.target.value)}
          type="text"
          id="hypothesis1"
          placeholder={t('clinicalChat.enterHypothesis1')}
        />
        <FormInput
          label={t('clinicalChat.hypothesis2')}
          value={hypotheses.hypothesis2}
          onChange={(e) => handleHypothesisChange('hypothesis2', e.target.value)}
          type="text"
          id="hypothesis2"
          placeholder={t('clinicalChat.enterHypothesis2')}
        />
        <FormInput
          label={t('clinicalChat.hypothesis3')}
          value={hypotheses.hypothesis3}
          onChange={(e) => handleHypothesisChange('hypothesis3', e.target.value)}
          type="text"
          id="hypothesis3"
          placeholder={t('clinicalChat.enterHypothesis3')}
        />
      <div className="mt-2 flex flex-col-reverse gap-2 border-t border-slate-200 pt-4 sm:flex-row sm:justify-end">
        <button
          type="button"
          onClick={onCancel}
          disabled={isSubmitting}
          className="rounded-lg px-5 py-2.5 text-sm font-medium text-slate-600 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {t('common.cancel')}
        </button>
        <button
          type="submit"
          disabled={!hasHypothesis || isSubmitting}
          className="rounded-lg bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-slate-300"
        >
          {isSubmitting ? t('common.loading') : t('clinicalChat.submit')}
        </button>
      </div>
    </form>
  );
};
