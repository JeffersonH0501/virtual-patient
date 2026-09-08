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
      <div className="flex flex-col h-full max-h-dialog-content rounded-2xl">
        <div className="p-4 border-b border-gray-200 bg-white rounded-t-2xl">
          <h2 className="text-lg font-semibold text-gray-800">
            {t('clinicalChat.welcome.title')}
          </h2>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          <div className="space-y-4">
            <p className="dialog-copy">
              {t('clinicalChat.welcome.description')}
            </p>
            <p className="dialog-copy dialog-info-callout">
              {t('clinicalChat.welcome.description4')}
            </p>
          </div>
        </div>
        <div className="flex justify-end rounded-b-2xl bg-white p-4">
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
