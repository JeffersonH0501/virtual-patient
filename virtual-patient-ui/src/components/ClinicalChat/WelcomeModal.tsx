import {FC} from 'react';
import {useTranslation} from 'react-i18next';
import {Modal} from '../common/Modal';

type WelcomeModalProps = {
  isOpen: boolean;
  onAccept: () => void;
  onCancel: () => void;
};

export const WelcomeModal: FC<WelcomeModalProps> = ({isOpen, onAccept, onCancel}) => {
  const {t} = useTranslation();

  return (
    <Modal
      open={isOpen}
      closeAction={() => undefined}
      closeOnOutsideClick={false}
      hasActions
      size="small"
      containerId="welcome-modal"
    >
      <div className="dialog-shell">
        <div className="dialog-header">
          <h2 className="dialog-title">
            {t('clinicalChat.welcome.title')}
          </h2>
        </div>

        <div className="dialog-content flex-1">
          <div className="space-y-4">
            <p className="dialog-copy">
              {t('clinicalChat.welcome.description')}
            </p>
            <p className="dialog-annotation">
              {t('clinicalChat.welcome.description4')}
            </p>
          </div>
        </div>
        <div className="dialog-footer">
          <div className="dialog-actions">
            <button
              type="button"
              onClick={onCancel}
              className="dialog-action dialog-action--secondary"
            >
              {t('clinicalChat.welcome.cancel')}
            </button>
            <button
              type="button"
              onClick={onAccept}
              className="dialog-action dialog-action--primary"
              autoFocus
            >
              {t('clinicalChat.welcome.accept')}
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
};

