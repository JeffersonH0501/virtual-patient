import {useEffect, useState} from 'react';
import {requestLearningMoments} from '../../services/evaluations/learningMoments';
import {LearningMoment} from '../../types/learningMoments';

export function useLearningMoments(interviewId: number, sourceRevision: string | undefined, enabled: boolean) {
  const [moments, setMoments] = useState<LearningMoment[]>([]);
  useEffect(() => {
    setMoments([]);
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
          setMoments(result.moments.slice(0, 3));
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
  return moments;
}
