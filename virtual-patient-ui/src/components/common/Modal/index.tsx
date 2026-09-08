import {RemoveScroll} from 'react-remove-scroll';
import {Portal, PortalProps} from '../Portal';
import {DURATION} from '../../constants/duration';
import {useOnOutsideClick} from '../../../hooks/useOnOutsideClick';
import {CSSProperties, FC, PropsWithChildren, useState} from 'react';

export type ModalSize = 'small' | 'medium' | 'large';

export type ModalProps = {
  open: boolean;
  containerId?: string;
  overlayOpacity?: number;
  closeAction: () => void | Promise<void>;
  closeOnOutsideClick?: boolean;
  size?: ModalSize;
  responsive?: boolean;
  mobileHeightInPx?: number;
  ariaLabel?: string;
  hasActions?: boolean;
} & Pick<PortalProps, 'keepAfter'>;

const MODAL_CONTAINER_ID = 'modal-container-id';
export const Modal: FC<PropsWithChildren<ModalProps>> = ({
  children,
  closeAction,
  containerId = MODAL_CONTAINER_ID,
  overlayOpacity,
  open = false,
  closeOnOutsideClick = true,
  size = 'medium',
  keepAfter,
  ariaLabel,
  hasActions = false,
}) => {
  const [elementReference, setElementReference] = useState<HTMLDivElement | null>();
  const canDismiss = !hasActions;
  useOnOutsideClick(
    canDismiss && closeOnOutsideClick ? closeAction : undefined,
    elementReference,
    !open,
  );

  return (
    <Portal
      open={open}
      containerId={containerId}
      onEscPress={canDismiss ? closeAction : () => undefined}
      unmountDebounce={DURATION.modals.long}
      keepAfter={keepAfter}
    >
      <div
        className={`modal-overlay fixed inset-0 z-modal flex h-screen w-screen items-center justify-center p-4 backdrop-blur-sm sm:p-8 ${
          open ? 'modal-overlay--open' : 'modal-overlay--closed'
        }`}
        style={overlayOpacity === undefined ? undefined : {'--modal-overlay-opacity': overlayOpacity} as CSSProperties}
      >
        <RemoveScroll>
          <div
            ref={setElementReference}
            role="dialog"
            aria-modal="true"
            aria-label={ariaLabel}
            className={`modal-panel modal-panel--${size} flex flex-col overflow-hidden rounded-panel border border-border bg-surface shadow-modal ${
              open ? 'modal-panel--open' : 'modal-panel--closed'
            }`}
          >
            {children}
          </div>
        </RemoveScroll>
      </div>
    </Portal>
  );
};
