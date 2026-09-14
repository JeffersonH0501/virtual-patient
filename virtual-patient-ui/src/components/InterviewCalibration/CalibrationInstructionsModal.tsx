import {FC} from 'react';
import {useTranslation} from 'react-i18next';
import {Modal} from '../common/Modal';

type CalibrationInstructionsModalProps = {
  isOpen: boolean;
  onAccept: () => void;
  onCancel: () => void;
};

export const CalibrationInstructionsModal: FC<CalibrationInstructionsModalProps> = ({
  isOpen,
  onAccept,
  onCancel,
}) => {
  const {t} = useTranslation();

  return (
    <Modal
      open={isOpen}
      closeAction={() => undefined}
      closeOnOutsideClick={false}
      hasActions
      size="small"
      containerId="calibration-instructions-modal"
    >
      <div className="dialog-shell">
        <div className="dialog-header">
          <h2 className="dialog-title">{t('calibration.instructions.title')}</h2>
        </div>

        <div className="dialog-content flex-1">
          <p className="dialog-copy">{t('calibration.instructions.description')}</p>
          <ul className="mt-4">
            <li>{t('calibration.instructions.camera')}</li>
            <li>{t('calibration.instructions.microphone')}</li>
            <li>{t('calibration.instructions.voice')}</li>
          </ul>
          <p className="dialog-annotation mt-4">{t('calibration.instructions.requirement')}</p>
        </div>

        <div className="dialog-footer">
          <div className="dialog-actions">
            <button type="button" onClick={onCancel} className="dialog-action dialog-action--secondary">
              {t('common.cancel')}
            </button>
            <button type="button" onClick={onAccept} className="dialog-action dialog-action--primary" autoFocus>
              {t('calibration.instructions.accept')}
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
};

