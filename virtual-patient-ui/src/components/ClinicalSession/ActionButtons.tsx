import {FC} from 'react';
import {useTranslation} from 'react-i18next';

type ActionButtonsProps = {
  onStartSession: () => void;
  isFormValid: boolean;
  onView?: () => void;
  onPreview?: () => void;
  onCalibrationPreview?: () => void;
  onGazePreview?: () => void;
  onCancel?: () => void;
};

export const ActionButtons: FC<ActionButtonsProps> = ({onStartSession, isFormValid, onView, onPreview, onCalibrationPreview, onGazePreview, onCancel}) => {
  const {t} = useTranslation();

  return (
    <div className="mt-inset flex w-full justify-end">
      <div className="dialog-actions">
        {onCancel && <button type="button" className="ui-button ui-button--secondary" onClick={onCancel}>
          {t('common.cancel')}
        </button>}
        {onView && <button type="button" className="ui-button ui-button--primary" onClick={onView}>
          {t('patientPreview.view')}
        </button>}
        {onPreview && <button type="button" className="ui-button ui-button--primary"
          disabled={!isFormValid} onClick={onPreview}>{t('patientPreview.try')}</button>}
        {onCalibrationPreview && <button type="button" className="ui-button ui-button--primary" onClick={onCalibrationPreview}>
          {t('patientPreview.calibrationTry')}
        </button>}
        {onGazePreview && <button type="button" className="ui-button ui-button--primary" onClick={onGazePreview}>
          {t('patientPreview.gazeTry')}
        </button>}
        {!onPreview && <button
          type="button"
          onClick={onStartSession}
          disabled={!isFormValid}
          className="ui-button ui-button--primary"
        >
          {t('clinicalSession.startSession')}
        </button>}
      </div>
    </div>
  );
};
