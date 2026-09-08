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
    <div className="flex flex-col overflow-hidden rounded-panel bg-surface text-left">
      <header className="border-b border-border px-5 py-3.5">
        <h2 id="modal-title" className="text-lg font-semibold text-slate-800">{title}</h2>
      </header>
      <div className="px-5 py-4">
        <p className="text-sm leading-6 text-slate-600">{description}</p>
      </div>
      <footer className="flex justify-end px-5 py-3.5">
        <div className="dialog-actions">
          <ModalButton variant="secondary" onClick={onCancel}>
            {t('clinicalChat.cancel')}
          </ModalButton>
          <ModalButton variant="primary" onClick={onConfirm} disabled={isLoading}>
            {isLoading ? t('clinicalChat.submitting') : t('clinicalChat.confirm')}
          </ModalButton>
        </div>
      </footer>
    </div>
  );
};
