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
    <div className="dialog-shell">
      <header className="dialog-header">
        <h2 id="modal-title" className="dialog-title">{title}</h2>
      </header>
      <div className="dialog-content">
        <p className="text-sm leading-6 text-slate-600">{description}</p>
      </div>
      <footer className="dialog-footer">
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

