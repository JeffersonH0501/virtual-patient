import {FC} from 'react';
import {useTranslation} from 'react-i18next';

type ActionButtonsProps = {
  onCancel: () => void;
  onStartSession: () => void;
  isFormValid: boolean;
};

export const ActionButtons: FC<ActionButtonsProps> = ({onCancel, onStartSession, isFormValid}) => {
  const {t} = useTranslation();

  return (
    <div className="mt-4 flex w-full justify-end border-t border-slate-200 pt-4">
      <div className="dialog-actions">
        <button
          type="button"
          onClick={onCancel}
          className="dialog-action dialog-action--secondary"
        >
          {t('clinicalSession.cancel')}
        </button>
        <button
          type="button"
          onClick={onStartSession}
          disabled={!isFormValid}
          className="dialog-action dialog-action--primary"
        >
          {t('clinicalSession.startSession')}
        </button>
      </div>
    </div>
  );
};
