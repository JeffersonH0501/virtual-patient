import {useEffect} from 'react';

export const ENTER_KEY_CODE = 13;
export const SHIFT_KEY_CODE = 16;
export const CTRL_KEY_CODE = 17;
export const ALT_KEY_CODE = 18;
export const ESC_KEY_CODE = 27;
export const SPACE_KEY_CODE = 32;

export const useOnKeyDown = (
  keyCode: number,
  onKeydown?: (event: KeyboardEvent) => void,
  skipEvent?: boolean,
) => {
  useEffect(() => {
    if (!onKeydown || skipEvent) return () => null;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.keyCode === keyCode) onKeydown(event);
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [keyCode, onKeydown, skipEvent]);
};
