import {FC} from 'react';
import {useTranslation} from 'react-i18next';
import {Button} from '../Button';
import {DialogShell} from '../Dialog';

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
  confirmVariant?: 'primary' | 'danger';
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
    <DialogShell
      title={title}
      onClose={onCancel}
      busy={isLoading}
      hasDismissAction
      actions={
        <>
          <Button variant="secondary" onClick={onCancel} disabled={isLoading}>
            {cancelLabel ?? t('common.cancel')}
          </Button>
          <Button variant={confirmVariant} onClick={onConfirm} disabled={isLoading}>
            {isLoading ? t('clinicalChat.submitting') : (confirmLabel ?? t('clinicalChat.confirm'))}
          </Button>
        </>
      }
    >
      <p className="text-neutral-600 default-text">{description}</p>
    </DialogShell>
  );
};
