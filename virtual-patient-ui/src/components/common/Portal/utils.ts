import {DurationInMs} from '../../../types';

/**
 * Before executing onPortalUnmount this
 * time is added to avoid race conditions
 * (removing the container before the portal
 * is closed)
 */
const PORTAL_UNMOUNT_DELAY = 100;

export const awaitPortalUnmount = (
  onPortalUnmount: () => void,
  unmountDebounce: DurationInMs,
): void => {
  const timer = setTimeout(() => {
    clearTimeout(timer);
    onPortalUnmount();
    /**
     * After unmountDebounce the Portal
     * content will be removed from the DOM
     * and then the Portal container will be
     * removed after 100 miliseconds that
     * to avoid race conditions.
     */
  }, unmountDebounce + PORTAL_UNMOUNT_DELAY);
};

export const createContainerHTMLElement = (containerId: string): HTMLDivElement => {
  const element = document.createElement('div');
  element.setAttribute('id', containerId);
  document.body.appendChild(element);

  return element;
};
