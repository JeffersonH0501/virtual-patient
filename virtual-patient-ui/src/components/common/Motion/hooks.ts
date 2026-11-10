import {
  AnimationEvent,
  createContext,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import {readDesignNumber, readDesignToken} from '../../../utils/designTokens';

export const MotionContext = createContext({enabled: false, reduced: false});
export const VisibilityContext = createContext(true);
export const useAppMotion = () => useContext(MotionContext);
export const useMotionVisibility = () => useContext(VisibilityContext);

/** Retain outgoing UI briefly; a new opening always cancels pending removal. */
export const usePresence = (
  open: boolean,
  exitToken: '--app-motion-exit' | '--app-motion-expand' = '--app-motion-exit',
) => {
  const {enabled, reduced} = useAppMotion();
  const [retained, setRetained] = useState(open);
  const currentOpen = useRef(open);
  currentOpen.current = open;
  const animate = enabled && !reduced;
  useEffect(() => {
    if (open) {
      setRetained(true);
      return;
    }
    if (!animate) {
      setRetained(false);
      return;
    }
    const timer = window.setTimeout(() => setRetained(false), readDesignNumber(exitToken));
    return () => window.clearTimeout(timer);
  }, [open, animate, exitToken]);
  const onAnimationEnd = (event: AnimationEvent<HTMLElement>) => {
    if (event.target === event.currentTarget && !currentOpen.current) setRetained(false);
  };
  return {present: open || (animate && retained), state: open ? 'open' : 'closed', onAnimationEnd};
};

/** Only newly mounted items enter; polling, reordering and playback never replay it. */
export const useEntrance = <T extends HTMLElement>(index = 0, slide = false) => {
  const element = useRef<T>(null);
  const completed = useRef(false);
  const initialIndex = useRef(index);
  const {enabled, reduced} = useAppMotion();
  useLayoutEffect(() => {
    if (completed.current) return;
    if (!enabled || reduced || !element.current?.animate) {
      completed.current = true;
      return;
    }
    const distance = readDesignToken('--app-motion-distance');
    const frames = slide
      ? [
          {opacity: 0, transform: `translateY(${distance})`},
          {opacity: 1, transform: 'translateY(0)'},
        ]
      : [{opacity: 0}, {opacity: 1}];
    const animation = element.current.animate(frames, {
      duration: readDesignNumber('--app-motion-enter'),
      delay: Math.min(
        Math.max(0, initialIndex.current) * readDesignNumber('--app-motion-stagger'),
        readDesignNumber('--app-motion-stagger-limit'),
      ),
      easing: readDesignToken('--motion-panel-easing'),
      fill: 'backwards',
    });
    animation.onfinish = () => {
      completed.current = true;
    };
    return () => animation.cancel();
  }, [enabled, reduced, slide]);
  return element;
};
