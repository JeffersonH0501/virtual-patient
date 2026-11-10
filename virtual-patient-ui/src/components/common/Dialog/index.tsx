import {FormEventHandler, PropsWithChildren, ReactNode, useId} from 'react';
import {useTranslation} from 'react-i18next';
import {X} from 'lucide-react';
import {Modal, ModalProps} from '../Modal';

type DialogShellProps = PropsWithChildren<{
  title: string;
  onClose?: () => void;
  busy?: boolean;
  actions?: ReactNode;
  /** The footer already provides Cancel, Close or an equivalent dismissal. */
  hasDismissAction?: boolean;
  onSubmit?: FormEventHandler<HTMLFormElement>;
}>;

/** Shared header, scrolling body and persistent actions for a focused task. */
export const DialogShell = ({
  title,
  onClose,
  busy = false,
  actions,
  hasDismissAction = false,
  onSubmit,
  children,
}: DialogShellProps) => {
  const {t} = useTranslation();
  const titleId = useId();
  const content = (
    <>
      <header className="dialog-header">
        <h2 id={titleId} className="dialog-title">
          {title}
        </h2>
        {onClose && !hasDismissAction && (
          <button
            type="button"
            className="dialog-close-button"
            disabled={busy}
            onClick={onClose}
            aria-label={t('common.close')}
          >
            <X />
          </button>
        )}
      </header>
      <div className="dialog-content">{children}</div>
      {actions && (
        <footer className="dialog-footer">
          <div className="dialog-actions">{actions}</div>
        </footer>
      )}
    </>
  );
  return onSubmit ? (
    <form className="dialog-shell" aria-labelledby={titleId} aria-busy={busy} onSubmit={onSubmit}>
      {content}
    </form>
  ) : (
    <div className="dialog-shell" aria-labelledby={titleId} aria-busy={busy}>
      {content}
    </div>
  );
};

type DialogProps = DialogShellProps &
  Pick<ModalProps, 'size' | 'containerId' | 'closeOnOutsideClick'> & {open?: boolean};

/** Modal behavior stays in Modal; visual structure is shared by every dialog. */
export const Dialog = ({
  open = true,
  size = 'small',
  containerId,
  closeOnOutsideClick = false,
  ...props
}: DialogProps) => (
  <Modal
    open={open}
    size={size}
    containerId={containerId}
    ariaLabel={props.title}
    hasActions={props.busy || !props.onClose}
    closeOnOutsideClick={closeOnOutsideClick}
    closeAction={() => {
      if (!props.busy) props.onClose?.();
    }}
  >
    <DialogShell {...props} />
  </Modal>
);
