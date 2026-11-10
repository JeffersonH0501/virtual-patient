import {Dialog} from '../common/Dialog';
import {FC} from 'react';
import {Trans, useTranslation} from 'react-i18next';

type WelcomeModalProps = {
  isOpen: boolean;
  onAccept: () => void;
  onCancel: () => void;
  busy?: boolean;
  error?: boolean;
};

export const WelcomeModal: FC<WelcomeModalProps> = ({isOpen, onAccept, onCancel, busy = false, error = false}) => {
  const {t} = useTranslation();

  return (
    <Dialog
      title={t('clinicalChat.welcome.title')}
      open={isOpen}
      onClose={onCancel}
      containerId="welcome-modal"
      hasDismissAction
      busy={busy}
      actions={
        <>
          <button type="button" onClick={onCancel} disabled={busy} className="ui-button ui-button--secondary">
            {t('clinicalChat.welcome.cancel')}
          </button>
          <button
            type="button"
            onClick={onAccept}
            disabled={busy}
            className="ui-button ui-button--primary"
            autoFocus
          >
            {t(busy ? 'common.loading' : 'clinicalChat.welcome.accept')}
          </button>
        </>
      }
    >
      <div className="space-y-layout">
        <p className="dialog-copy">{t('clinicalChat.welcome.description')}</p>
        <ul className="dialog-list dialog-copy">
          {['scope', 'duration', 'evaluation'].map((instruction) =>
            <li key={instruction}><Trans i18nKey={`clinicalChat.welcome.${instruction}`} /></li>)}
        </ul>
        {error && <p className="dialog-copy text-danger-700" role="alert">{t('calibration.startError')}</p>}
      </div>
    </Dialog>
  );
};
