import {useEffect, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {getClinicalCaseById} from '../../services/clinicalCases';
import {Button} from '../common/Button';
import {CaseRecord} from './CaseRecord';
import {Dialog} from '../common/Dialog';
import {gradingRequest} from '../../services/teacherGrading';

type CaseDetailsDialogProps = ({caseId: number; interviewId?: never} | {interviewId: number; caseId?: never}) & {onClose: () => void};

export const CaseDetailsDialog = ({caseId, interviewId, onClose}: CaseDetailsDialogProps) => {
  const {t} = useTranslation();
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let active = true;
    setData(null);
    setFailed(false);
    const request = interviewId === undefined ? getClinicalCaseById(String(caseId))
      : gradingRequest<Record<string, unknown>>(`/medical-interviews/${interviewId}/clinical-case`);
    void request.then((result) => {
      if (active) setData(result);
    }).catch(() => {
      if (active) setFailed(true);
    });
    return () => {
      active = false;
    };
  }, [caseId, interviewId, attempt]);

  return <Dialog title={t('caseManagement.detail')} size="large" onClose={onClose}>
    {failed ? (
      <div className="ui-form-stack">
        <p className="text-danger-700 default-text" role="alert">{t('clinicalCases.failedToLoad')}</p>
        <div className="ui-button-group">
          <Button variant="secondary" onClick={() => setAttempt((previous) => previous + 1)}>{t('common.retry')}</Button>
        </div>
      </div>
    ) : data ? <CaseRecord data={data} reading /> : <p role="status" className="text-content-muted default-text">{t('common.loading')}</p>}
  </Dialog>;
};
