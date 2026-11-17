import {useEffect, useState} from 'react';
import {requestLearningMoments} from '../../services/evaluations/learningMoments';
import {LearningMoment} from '../../types/learningMoments';

export type LearningMomentsView = {
  moments: LearningMoment[];
  /** True only when generation completed for the current evaluation, so an empty list means "none found". */
  ready: boolean;
};

const NOT_READY: LearningMomentsView = {moments: [], ready: false};

export function useLearningMoments(interviewId: number, sourceRevision: string | undefined, enabled: boolean): LearningMomentsView {
  const [view, setView] = useState<LearningMomentsView>(NOT_READY);
  useEffect(() => {
    setView(NOT_READY);
    if (!enabled) return;
    let disposed = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const result = await requestLearningMoments(interviewId);
        if (disposed) return;
        if (result.status === 'pending' || result.status === 'processing') {
          timer = setTimeout(() => void load(), 2000);
        } else if (result.status === 'completed' && !result.stale) {
          setView({moments: result.moments, ready: true});
        }
      } catch {
        // Category feedback remains available if supplemental moments cannot load.
      }
    }
    void load();
    return () => {
      disposed = true;
      clearTimeout(timer);
    };
  }, [interviewId, sourceRevision, enabled]);
  return view;
}
