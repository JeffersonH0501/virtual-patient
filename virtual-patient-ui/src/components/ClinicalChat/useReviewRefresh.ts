import {useCallback, useEffect, useRef, useState} from 'react';
import {
  getInterviewRecap,
  reprocessInterviewRecording,
  regenerateInterviewEvaluation,
} from '../../services/recordings';
import {InterviewRecap as InterviewRecapData} from '../../types/recording';
import {User} from '../../types/user';

type Options = {
  interviewId: number | null;
  role: User['role'] | undefined;
  mode: 'session' | 'review';
  isCompleted: boolean;
  recapData: InterviewRecapData | null;
  setRecapData: (recap: InterviewRecapData) => void;
  fetchInterview: () => Promise<unknown>;
};

export const useReviewRefresh = ({
  interviewId,
  role,
  mode,
  isCompleted,
  recapData,
  setRecapData,
  fetchInterview,
}: Options) => {
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [isReprocessing, setIsReprocessing] = useState(false);
  const [refreshError, setRefreshError] = useState(false);
  const regenerateActiveRef = useRef(false);
  const refreshAbortRef = useRef<AbortController | null>(null);
  const handleRefresh = useCallback(
    async (observations: boolean) => {
      if (
        !interviewId ||
        role !== 'superuser' ||
        mode !== 'review' ||
        !isCompleted ||
        regenerateActiveRef.current
      ) {
        return;
      }
      regenerateActiveRef.current = true;
      const controller = new AbortController();
      refreshAbortRef.current = controller;
      setRefreshError(false);
      if (observations) setIsReprocessing(true);
      else setIsRegenerating(true);
      const PENDING_STATUSES = ['queued', 'processing'];
      const POLL_INTERVAL_MS = 3000;
      const MAX_POLLS = observations ? 800 : 200;
      try {
        if (observations) await reprocessInterviewRecording(interviewId);
        else await regenerateInterviewEvaluation(interviewId);
        if (controller.signal.aborted) return;
        let finished = false;
        // The evaluation lifecycle remains pending while the LLM is running.
        for (let polls = 0; polls < MAX_POLLS; polls += 1) {
          await new Promise<void>((resolve) => {
            const done = () => {
              window.clearTimeout(timer);
              controller.signal.removeEventListener('abort', done);
              resolve();
            };
            const timer = window.setTimeout(done, POLL_INTERVAL_MS);
            controller.signal.addEventListener('abort', done, {once: true});
          });
          if (controller.signal.aborted) return;
          let status: string | undefined;
          try {
            const recap = await getInterviewRecap(interviewId, controller.signal);
            if (controller.signal.aborted) return;
            setRecapData(recap);
            status = recap.evaluationProcessing?.status;
          } catch (error) {
            if (controller.signal.aborted) return;
            console.error('Failed to poll regeneration status:', error);
          }
          if (status && !PENDING_STATUSES.includes(status)) {
            if (status === 'failed') throw new Error('Review refresh failed');
            finished = true;
            break;
          }
        }
        if (controller.signal.aborted) return;
        if (!finished) throw new Error('Review refresh timed out');
        await fetchInterview();
      } catch (error) {
        if (controller.signal.aborted) return;
        console.error('Failed to regenerate evaluation:', error);
        setRefreshError(true);
      } finally {
        if (refreshAbortRef.current === controller) {
          refreshAbortRef.current = null;
          regenerateActiveRef.current = false;
          setIsRegenerating(false);
          setIsReprocessing(false);
        }
      }
    },
    [fetchInterview, interviewId, role, mode, isCompleted],
  );

  const previousEvaluationStatusRef = useRef<string | undefined>(undefined);
  useEffect(() => {
    const previous = previousEvaluationStatusRef.current;
    const current = recapData?.interviewId === interviewId ? recapData.evaluationProcessing?.status : undefined;
    previousEvaluationStatusRef.current = current;
    if (
      (previous === 'queued' || previous === 'processing') &&
      current &&
      current !== 'queued' &&
      current !== 'processing' &&
      !regenerateActiveRef.current
    ) {
      if (current === 'failed') setRefreshError(true);
      else void fetchInterview();
    }
  }, [recapData?.interviewId, recapData?.evaluationProcessing?.status, interviewId, fetchInterview]);

  // If the review screen unmounts mid-regeneration, stop the poll loop.
  useEffect(() => {
    setIsRegenerating(false);
    setIsReprocessing(false);
    setRefreshError(false);
    previousEvaluationStatusRef.current = undefined;
    return () => {
      refreshAbortRef.current?.abort();
      refreshAbortRef.current = null;
      regenerateActiveRef.current = false;
    };
  }, [interviewId, role, mode]);

  return {isRegenerating, isReprocessing, refreshError, handleRefresh};
};
