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
    <div className="flex flex-wrap gap-7 self-end pl-20 mt-3 text-base text-center max-md:pl-5">
      <button
        onClick={onCancel}
        className="px-4 pt-3 pb-4 text-black whitespace-nowrap hover:bg-gray-100 transition-colors duration-200"
      >
        {t('clinicalSession.cancel')}
      </button>
      <button
        onClick={onStartSession}
        disabled={!isFormValid}
        className={`flex gap-1 px-5 py-3 text-white rounded-lg max-md:pl-5 transition-colors duration-200 ${
          isFormValid 
            ? 'bg-blue-600 hover:bg-blue-700 cursor-pointer' 
            : 'bg-gray-400 cursor-not-allowed'
        }`}
      >
        <span className="grow">{t('clinicalSession.startSession')}</span>
      </button>
    </div>
  );
};
