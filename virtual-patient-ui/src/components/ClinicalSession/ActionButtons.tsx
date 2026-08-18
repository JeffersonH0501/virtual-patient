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
    <div className="mt-4 grid grid-cols-2 gap-2 border-t border-slate-200 pt-4 text-sm sm:flex sm:flex-wrap sm:justify-end">
      <button
        type="button"
        onClick={onCancel}
        className="w-full rounded-lg px-3 py-2 text-slate-600 transition-colors hover:bg-slate-100 sm:w-auto sm:px-4"
      >
        {t('clinicalSession.cancel')}
      </button>
      <button
        type="button"
        onClick={onStartSession}
        disabled={!isFormValid}
        className={`w-full rounded-lg px-3 py-2 font-semibold text-white transition-colors sm:w-auto sm:px-5 ${
          isFormValid
            ? 'cursor-pointer bg-blue-600 hover:bg-blue-700'
            : 'bg-gray-400 cursor-not-allowed'
        }`}
      >
        {t('clinicalSession.startSession')}
      </button>
    </div>
  );
};
