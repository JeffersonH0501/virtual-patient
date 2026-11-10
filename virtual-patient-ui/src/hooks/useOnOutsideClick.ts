import {useEffect} from 'react';

type InsideElement = HTMLElement | null;

export const useOnOutsideClick = (
  onOutsideClick?: (event: MouseEvent) => void,
  insideElement?: InsideElement | InsideElement[],
  disableHandler: boolean = false,
) => {
  useEffect(() => {
    if (!insideElement || !onOutsideClick || disableHandler) return () => null;

    const handleMouseUp = (event: MouseEvent) => {
      const target = event.target as Node | null;
      if (!target) return;

      const insideElementArray = Array.isArray(insideElement)
        ? [...insideElement]
        : [insideElement];
      const ownerId = target instanceof Element ? target.closest('[data-ui-select-owner]')?.getAttribute('data-ui-select-owner') : null;
      const owner = ownerId ? document.getElementById(ownerId) : null;
      if (!insideElementArray.some((element) => element && (element.contains(target) || (owner && element.contains(owner))))) {
        onOutsideClick(event);
      }
    };

    document.addEventListener('mouseup', handleMouseUp);
    return () => document.removeEventListener('mouseup', handleMouseUp);
  }, [insideElement, onOutsideClick, disableHandler]);
};
