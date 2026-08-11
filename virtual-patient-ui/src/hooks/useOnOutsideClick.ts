import {useEffect} from 'react';

type InsideElement = HTMLElement | null;

export const REACT_SELECT_CLASS_NAME_PREFIX = 'rscnp';
export const REACT_SELECT_PORTAL_CLASS_NAME = `${REACT_SELECT_CLASS_NAME_PREFIX}__menu-portal`;

export const useOnOutsideClick = (
  onOutsideClick?: (event: MouseEvent) => void,
  insideElement?: InsideElement | InsideElement[],
  disableHandler: boolean = false,
) => {
  useEffect(() => {
    if (!insideElement || !onOutsideClick || disableHandler) return () => null;

    const handleMouseUp = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      if (!target) return;

      let insideElementArray: InsideElement[];
      if (!Array.isArray(insideElement)) insideElementArray = [insideElement];
      else insideElementArray = insideElement;

      insideElementArray.push(document.querySelector(`.${REACT_SELECT_PORTAL_CLASS_NAME}`));
      if (!insideElementArray.some((element) => element && element.contains(target))) {
        onOutsideClick(event);
      }
    };

    document.addEventListener('mouseup', handleMouseUp);
    return () => document.removeEventListener('mouseup', handleMouseUp);
  }, [insideElement, onOutsideClick, disableHandler]);
};
