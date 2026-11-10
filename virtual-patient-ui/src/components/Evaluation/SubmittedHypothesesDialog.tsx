import {useEffect, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Dialog} from '../common/Dialog';
import {Button} from '../common/Button';
import {gradingRequest} from '../../services/teacherGrading';

type Hypothesis = {id: number; hypothesisText: string; hypothesisOrder: number};

export function SubmittedHypothesesDialog({interviewId, onClose}: {interviewId: number; onClose: () => void}) {
  const {t} = useTranslation();
  const [items, setItems] = useState<Hypothesis[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setItems(null); setFailed(false);
    void gradingRequest<Hypothesis[]>(`/medical-interviews/${interviewId}/hypotheses`).then((result) => {
      if (active) setItems(result);
    }).catch(() => { if (active) setFailed(true); });
    return () => { active = false; };
  }, [interviewId, attempt]);
  return <Dialog title={t('clinicalChat.submittedHypotheses')} size="large" onClose={onClose}>
    {failed ? <div className="ui-form-stack"><p className="ui-notice ui-notice--danger" role="alert">{t('grading.hypothesesLoadError')}</p><div className="ui-button-group"><Button variant="secondary" onClick={() => setAttempt((value) => value + 1)}>{t('common.retry')}</Button></div></div>
      : items === null ? <p role="status">{t('common.loading')}</p>
      : items.length ? <ol className="numbered-list space-y-1">{[...items].sort((a, b) => a.hypothesisOrder - b.hypothesisOrder).map((item) => <li key={item.id}>{item.hypothesisText}</li>)}</ol>
      : <p>{t('grading.noSubmittedHypotheses')}</p>}
  </Dialog>;
}
