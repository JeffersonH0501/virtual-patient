import {FC} from 'react';
import {useTranslation} from 'react-i18next';
import {ModalButton} from './ModalButton';

type Props = {
  title: string;
  description: string;
  onCancel: () => void;
  onConfirm: () => void;
  isLoading?: boolean;
  /** Overrides the default cancel button label. */
  cancelLabel?: string;
  /** Overrides the default confirm button label. */
  confirmLabel?: string;
  /** Visual style of the confirm button. Defaults to the primary style. */
  confirmVariant?: 'primary' | 'warning';
};

export const ConfirmationModal: FC<Props> = ({
  title,
  description,
  onCancel,
  onConfirm,
  isLoading = false,
  cancelLabel,
  confirmLabel,
  confirmVariant = 'primary',
}) => {
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
            {cancelLabel ?? t('clinicalChat.cancel')}
          </ModalButton>
          <ModalButton variant={confirmVariant} onClick={onConfirm} disabled={isLoading}>
            {isLoading ? t('clinicalChat.submitting') : (confirmLabel ?? t('clinicalChat.confirm'))}
          </ModalButton>
        </div>
      </footer>
    </div>
  );
};

