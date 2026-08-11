import {FC} from 'react';
import {useTranslation} from 'react-i18next';
import {ModalButton} from './ModalButton';

type Props = {
  title: string;
  description: string;
  onCancel: () => void;
  onConfirm: () => void;
  isLoading?: boolean;
};

export const ConfirmationModal: FC<Props> = ({title, description, onCancel, onConfirm, isLoading = false}) => {
  const {t} = useTranslation();
  
  return (
    <div className="fixed inset-0 bg-opacity-50 overflow-y-auto h-full w-full flex items-center justify-center">
      <div className="flex flex-col rounded-2xl max-w-[796px] bg-white p-6">
        <h2 id="modal-title" className="mb-5 text-xl font-bold text-gray-800">
          {title}
        </h2>
        <p className="mb-6 text-base text-gray-600">{description}</p>
        <div className="flex gap-5 justify-end max-sm:justify-center max-sm:w-full">
          <ModalButton variant="secondary" onClick={onCancel}>
            {t('clinicalChat.cancel')}
          </ModalButton>
          <ModalButton variant="primary" onClick={onConfirm} disabled={isLoading}>
            {isLoading ? t('clinicalChat.submitting') : t('clinicalChat.confirm')}
          </ModalButton>
        </div>
      </div>
    </div>
  );
};
