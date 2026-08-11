import {FC, PropsWithChildren as WithChildren, useState, useEffect} from 'react';
import * as ReactDOM from 'react-dom';

import {useDebounce, useOnKeyDown, useOnOutsideClick} from '../../../hooks/';
import {ESC_KEY_CODE} from '../../../hooks/useOnKeyDown';
import {DurationInMs} from '../../../types';
import {awaitPortalUnmount, createContainerHTMLElement} from './utils';

export type PortalProps = {
  open: boolean;
  containerId: string;
  onOutsideClick?: (event?: MouseEvent) => void;
  onEscPress?: (event?: KeyboardEvent) => void;
  unmountDebounce?: DurationInMs;
  keepAfter?: boolean;
};

export const Portal: FC<WithChildren<PortalProps>> = ({
  open,
  containerId,
  onOutsideClick,
  onEscPress,
  unmountDebounce = 0,
  keepAfter = false,
  children,
}) => {
  const [container, setContainer] = useState<HTMLElement>();
  /**
   * debouncedOpen is only meant to keep the portal while the unmount
   * animation ends.
   */
  const debounceDelay = open ? 0 : unmountDebounce;
  const debouncedOpen = useDebounce(open, debounceDelay);

  useOnKeyDown(ESC_KEY_CODE, onEscPress, !open);
  useOnOutsideClick(onOutsideClick, container, !open);

  useEffect(() => {
    return () => {
      if (!container) return;

      /**
       * If the container HTML Element is empty after closing
       * the Portal we probably injected it to the DOM just to
       * render the Portal, so we remove it in that case (after
       * making sure the Portal content was removed). You can
       * overwrite this behavior with the `keepAfter` prop.
       */
      awaitPortalUnmount(() => {
        if (!keepAfter && container.innerHTML === '') container.remove();
      }, unmountDebounce);
    };
  }, []);

  useEffect(() => {
    if (!open) return;

    setContainer(document.getElementById(containerId) || createContainerHTMLElement(containerId));
  }, [open, containerId]);

  return (open || debouncedOpen) && container ? ReactDOM.createPortal(children, container) : null;
};
