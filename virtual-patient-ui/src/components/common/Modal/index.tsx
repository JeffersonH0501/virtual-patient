import {RemoveScroll} from 'react-remove-scroll';
import {Portal, PortalProps} from '../Portal';
import {DURATION} from '../../constants/duration';
import {useOnOutsideClick} from '../../../hooks/useOnOutsideClick';
import {CSSProperties, FC, PropsWithChildren, useLayoutEffect, useId, useRef, useState} from 'react';
import {useAppMotion, useMotionVisibility, usePresence} from '../Motion/hooks';

export type ModalSize = 'small' | 'medium' | 'large';

export type ModalProps = {
  open: boolean;
  containerId?: string;
  overlayOpacity?: number;
  closeAction: () => void | Promise<void>;
  closeOnOutsideClick?: boolean;
  size?: ModalSize;
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
  size = 'small',
  keepAfter,
  ariaLabel,
  hasActions = false,
}) => {
  const [elementReference, setElementReference] = useState<HTMLDivElement | null>();
  const motion = useAppMotion();
  const visible = useMotionVisibility();
  open = open && visible;
  const presence = usePresence(open);
  const mounted = motion.enabled ? presence.present : open;
  const openReference = useRef(open);
  openReference.current = open;
  const titleId = useId();
  const returnFocus = useRef<HTMLElement | null>(null);
  useLayoutEffect(() => {
    if (!open) return;
    returnFocus.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    return () => {
      const trigger = returnFocus.current;
      queueMicrotask(() => {
        if (trigger?.isConnected && (!openReference.current || !elementReference?.isConnected)) trigger.focus({preventScroll: true});
      });
    };
  }, [open]);
  const canDismiss = !hasActions;
  useLayoutEffect(() => {
    if (!open || !mounted || !elementReference) return;
    const heading = elementReference.querySelector('h1, h2, h3, .default-title');
    if (!ariaLabel && heading) {
      if (!heading.id) heading.id = titleId;
      elementReference.setAttribute('aria-labelledby', heading.id);
    }
    const focusable = () =>
      Array.from(
        elementReference.querySelectorAll<HTMLElement>(
          'button:not(:disabled), a[href], input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]',
        ),
      ).filter(
        (element) =>
          element.tabIndex >= 0 &&
          !element.closest('[hidden], [inert], [aria-hidden="true"]') &&
          getComputedStyle(element).display !== 'none' &&
          getComputedStyle(element).visibility !== 'hidden',
      );
    const isTopDialog = () => {
      const dialogs = document.querySelectorAll('[role="dialog"][data-modal-open="true"]');
      return dialogs[dialogs.length - 1] === elementReference;
    };
    (focusable()[0] ?? elementReference).focus({preventScroll: true});
    const handleKey = (event: KeyboardEvent) => {
      if (!openReference.current || event.key !== 'Tab' || !isTopDialog()) return;
      const elements = focusable();
      const first = elements[0] ?? elementReference;
      const last = elements[elements.length - 1] ?? elementReference;
      if (
        elements.length === 0 ||
        (event.shiftKey && document.activeElement === first) ||
        (!event.shiftKey && document.activeElement === last)
      ) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      }
    };
    const containFocus = (event: FocusEvent) => {
      if (
        openReference.current &&
        isTopDialog() &&
        event.target instanceof Node &&
        !elementReference.contains(event.target)
      ) {
        (focusable()[0] ?? elementReference).focus();
      }
    };
    document.addEventListener('keydown', handleKey);
    document.addEventListener('focusin', containFocus);
    return () => {
      document.removeEventListener('keydown', handleKey);
      document.removeEventListener('focusin', containFocus);
    };
  }, [open, elementReference, mounted, ariaLabel, titleId]);
  useOnOutsideClick(
    canDismiss && closeOnOutsideClick ? closeAction : undefined,
    elementReference,
    !open,
  );

  return (
    <Portal
      open={mounted}
      containerId={containerId}
      onEscPress={open && canDismiss ? closeAction : undefined}
      unmountDebounce={motion.enabled ? 0 : DURATION.modals.long}
      keepAfter={keepAfter}
    >
      <div
        data-ui-motion={motion.enabled ? 'app' : undefined}
        data-motion-state={presence.state}
        onAnimationEnd={presence.onAnimationEnd}
        aria-hidden={!open || undefined}
        inert={!open}
        className={`modal-overlay fixed inset-x-0 z-modal flex w-full items-center justify-center p-inset backdrop-blur-sm sm:p-inset ${
          open ? 'modal-overlay--open' : 'modal-overlay--closed'
        }`}
        style={
          overlayOpacity === undefined
            ? undefined
            : ({'--modal-overlay-opacity': overlayOpacity} as CSSProperties)
        }
      >
        <RemoveScroll data-ui-select-portal-host>
          <div
            ref={setElementReference}
            role="dialog"
            tabIndex={-1}
            data-modal-open={open}
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
