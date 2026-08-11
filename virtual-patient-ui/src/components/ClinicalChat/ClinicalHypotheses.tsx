import {FC, FormEvent, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {FormInput, Modal} from '../common/';
import {useParams} from 'react-router-dom';
import {SubmitHypothesis} from './SubmitHypothesis';
import {createHypothesis} from '../../services/hypotheses';
import {completeInterview} from '../../services/interviews';
import {CreateHypothesisRequest} from '../../types/hypothesis';
import {InterviewEvaluationResponse} from '../../types/evaluation';

type ClinicalHypothesesProps = {
  onHypothesesSubmitted?: (evaluationData: InterviewEvaluationResponse) => void;
};

export const ClinicalHypotheses: FC<ClinicalHypothesesProps> = ({ onHypothesesSubmitted }) => {
  const {t} = useTranslation();
  const [openSubmitConfirmationModal, setOpenSubmitConfirmationModal] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [hypotheses, setHypotheses] = useState({
    hypothesis1: '',
    hypothesis2: '',
    hypothesis3: '',
  });
  const { interviewId: interviewIdParam } = useParams<{ interviewId: string }>();
  const interviewId = interviewIdParam ? parseInt(interviewIdParam, 10) : null;

  const handleHypothesisChange = (field: keyof typeof hypotheses, value: string) => {
    setHypotheses((prev) => ({
      ...prev,
      [field]: value,
    }));
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setOpenSubmitConfirmationModal(true);
  };

  const close = () => {
    setOpenSubmitConfirmationModal(false);
  };

  const submitHypotheses = async () => {
    if (!interviewId) {
      console.error('No interview ID found');
      return;
    }

    setIsSubmitting(true);
    try {
      // Filter out empty hypotheses and create the request
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

      // Call the API to submit hypotheses
      await createHypothesis(interviewId.toString(), hypothesesToSubmit);
      
      // Call the complete interview endpoint to get evaluation data
      const evaluationData = await completeInterview(interviewId.toString());
      
      // Close the modal
      setOpenSubmitConfirmationModal(false);
      
      // Call the callback to show evaluation modal with the evaluation data
      if (onHypothesesSubmitted) {
        onHypothesesSubmitted(evaluationData);
      }
    } catch (error) {
      console.error('Failed to submit hypotheses:', error);
      // You might want to show an error message to the user here
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <>
      <form
        onSubmit={handleSubmit}
        className="flex flex-col gap-4 w-[647px] p-8 max-md:px-5 max-md:py-0 max-md:w-full max-sm:px-4 max-sm:py-0 w-full"
      >
        <h2 className="mb-6 text-xl font-bold tracking-tighter text-neutral-900 text-left">
          {t('clinicalChat.clinicalHypotheses')}
        </h2>
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
        <button
          type="submit"
          className="ml-auto text-base text-white bg-blue-600 rounded-lg cursor-pointer border-[none] w-[114px] max-sm:w-full hover:bg-blue-700 transition-colors"
        >
          {t('clinicalChat.submit')}
        </button>
      </form>
      <Modal
        size="medium"
        open={openSubmitConfirmationModal}
        closeAction={close}
        closeOnOutsideClick
      >
        <SubmitHypothesis onCancel={close} onConfirm={submitHypotheses} isLoading={isSubmitting} />
      </Modal>
    </>
  );
};
