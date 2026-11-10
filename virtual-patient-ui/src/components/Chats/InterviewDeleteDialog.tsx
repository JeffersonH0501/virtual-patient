import {Dialog} from '../common/Dialog';
import {useTranslation} from 'react-i18next';
import {Button} from '../common';

type Props = {
  interviewId: number | null;
  busy: boolean;
  error: string | null;
  onCancel: () => void;
  onConfirm: () => void;
};

export const InterviewDeleteDialog = ({interviewId, busy, error, onCancel, onConfirm}: Props) => {
  const {t} = useTranslation();
  return (
    <Dialog
      title={t('conversations.deleteInterviewTitle')}
      open={interviewId !== null}
      onClose={onCancel}
      busy={busy}
      hasDismissAction
      actions={
        <>
          <Button variant="secondary" disabled={busy} onClick={onCancel}>
            {t('common.cancel')}
          </Button>
          <Button variant="danger" disabled={busy} onClick={onConfirm}>
            {t(busy ? 'conversations.deletingInterview' : 'common.delete')}
          </Button>
        </>
      }
    >
      <p>{t('conversations.deleteInterviewDescription', {id: interviewId})}</p>
      {error && (
        <p role="alert" className="mt-layout text-danger-600 default-text">
          {error}
        </p>
      )}
    </Dialog>
  );
};
