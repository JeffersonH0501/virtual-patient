import {Dialog} from './Dialog';
import {useRef, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {gradingRequest} from '../../services/teacherGrading';
import {Button} from './index';

export const AdministrativeDeleteDialog = ({
  path,
  name,
  onClose,
  onDeleted,
}: {
  path: string;
  name: string;
  onClose: () => void;
  onDeleted: () => void;
}) => {
  const {t} = useTranslation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const sending = useRef(false);
  const remove = async () => {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setError('');
    try {
      await gradingRequest(path, 'DELETE');
      onDeleted();
    } catch (failure) {
      setError(
        t(
          failure instanceof Error && /Wait for|processing|outside/.test(failure.message)
            ? 'administration.blocked'
            : 'administration.failed',
        ),
      );
    } finally {
      sending.current = false;
      setBusy(false);
    }
  };
  return (
    <Dialog
      title={t('common.delete')}
      onClose={onClose}
      busy={busy}
      hasDismissAction
      actions={
        <>
          <Button variant="secondary" disabled={busy} onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button variant="danger" disabled={busy} onClick={() => void remove()}>
            {t('common.delete')}
          </Button>
        </>
      }
    >
      <p>{t('administration.confirm', {name})}</p>
      {error && (
        <p role="alert" className="ui-notice ui-notice--danger">
          {error}
        </p>
      )}
    </Dialog>
  );
};
