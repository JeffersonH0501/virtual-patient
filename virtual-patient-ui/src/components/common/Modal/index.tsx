import {RemoveScroll} from 'react-remove-scroll';
import {Portal, PortalProps} from '../Portal';
import {DURATION} from '../../constants/duration';
import {useOnOutsideClick} from '../../../hooks/useOnOutsideClick';
import {FC, PropsWithChildren, useState} from 'react';

export type Size = 'extraSmall' | 'small' | 'medium' | 'large' | 'extraLarge';
export type ModalSize = Extract<Size, 'small' | 'medium' | 'large' | 'extraLarge'> | 'fullScreen';

export type ModalProps = {
  open: boolean;
  containerId?: string;
  overlayOpacity?: number;
  closeAction: () => void | Promise<void>;
  closeOnOutsideClick?: boolean;
  size?: ModalSize;
  responsive?: boolean;
  mobileHeightInPx?: number;
} & Pick<PortalProps, 'keepAfter'>;

const MODAL_CONTAINER_ID = 'modal-container-id';
const DEFAULT_MODAL_OPACITY = 0.3;

const MODAL_SIZES = {
  small: {width: '448px', height: 'auto'},
  medium: {width: '480px', height: 'auto'},
  large: {width: '880px', height: '480px'},
  extraLarge: {width: 'min(96vw, 1760px)', height: 'auto'},
  fullScreen: {width: '100%', height: '100vh'},
};

export const Modal: FC<PropsWithChildren<ModalProps>> = ({
  children,
  closeAction,
  containerId = MODAL_CONTAINER_ID,
  overlayOpacity = DEFAULT_MODAL_OPACITY,
  open = false,
  closeOnOutsideClick = true,
  size = 'medium',
  keepAfter,
}) => {
  const [elementReference, setElementReference] = useState<HTMLDivElement | null>();
  useOnOutsideClick(closeOnOutsideClick ? closeAction : undefined, elementReference, !open);

  return (
    <Portal
      open={open}
      containerId={containerId}
      onEscPress={closeAction}
      unmountDebounce={DURATION.modals.short}
      keepAfter={keepAfter}
    >
      <div
        className="fixed inset-0 z-[100] flex h-screen w-screen items-center justify-center p-4"
        style={{backgroundColor: `rgba(0, 0, 0, ${overlayOpacity})`}}
      >
        <RemoveScroll>
          <div
            ref={setElementReference}
            className={`flex flex-col bg-white shadow-dropdown rounded-2xl ${
              size === 'fullScreen' ? 'top-0 right-0 rounded-none overflow-scroll absolute' : ''
            }`}
            style={{
              width: MODAL_SIZES[size!].width,
              height: MODAL_SIZES[size!].height,
              maxHeight: size === 'fullScreen' ? '100vh' : size === 'extraLarge' ? 'calc(100dvh - 64px)' : '90vh',
            }}
          >
            {children}
          </div>
        </RemoveScroll>
      </div>
    </Portal>
  );
};
