import {
  CSSProperties,
  HTMLAttributes,
  PropsWithChildren,
  ReactNode,
  useEffect,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from 'react';
import {MotionContext, VisibilityContext, useAppMotion, usePresence, useEntrance} from './hooks';
import {readDesignNumber, readDesignToken} from '../../../utils/designTokens';
import {ChevronRight} from 'lucide-react';

export const MotionProvider = ({children}: PropsWithChildren) => {
  const [reduced, setReduced] = useState(
    () =>
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches,
  );
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return;
    const preference = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(preference.matches);
    preference.addEventListener('change', update);
    return () => preference.removeEventListener('change', update);
  }, []);
  return (
    <MotionContext.Provider value={{enabled: true, reduced}}>{children}</MotionContext.Provider>
  );
};

/** Preserve conditionally rendered dialogs through their exit, without cloning DOM. */
export const MotionPresence = ({visible, children}: {visible: boolean; children: ReactNode}) => {
  const presence = usePresence(visible);
  const content = useRef(children);
  if (visible) content.current = children;
  return presence.present ? (
    <VisibilityContext.Provider value={visible}>{content.current}</VisibilityContext.Provider>
  ) : null;
};

/** Fade new content without keying or remounting its live subtree. */
export const MotionContent = ({
  changeKey,
  children,
  className = '',
  slide = false,
  tabIndex,
}: PropsWithChildren<{changeKey?: string | number; className?: string; slide?: boolean; tabIndex?: number}>) => {
  const {enabled, reduced} = useAppMotion();
  const element = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    if (changeKey === undefined || !enabled || reduced || !element.current?.animate) return;
    const distance = readDesignToken('--app-motion-distance');
    const frames = slide
      ? [
          {opacity: 0, transform: `translateY(${distance})`},
          {opacity: 1, transform: 'translateY(0)'},
        ]
      : [{opacity: 0}, {opacity: 1}];
    const animation = element.current.animate(frames, {
      duration: readDesignNumber('--app-motion-enter'),
      easing: readDesignToken('--motion-panel-easing'),
    });
    return () => animation.cancel();
  }, [changeKey, enabled, reduced, slide]);
  return (
    <div ref={element} className={className} tabIndex={tabIndex}>
      {children}
    </div>
  );
};

/** Native table rows fade without transforms that could disturb cell alignment. */
export const MotionRow = ({
  entranceIndex = 0,
  ...props
}: HTMLAttributes<HTMLTableRowElement> & {entranceIndex?: number}) => {
  const element = useEntrance<HTMLTableRowElement>(entranceIndex);
  return <tr ref={element} {...props} />;
};

/** Keep native details semantics while retaining the open surface through its closing height. */
export const MotionDetails = ({
  summary,
  children,
  className,
  defaultOpen = false,
}: PropsWithChildren<{summary: ReactNode; className?: string; defaultOpen?: boolean}>) => {
  const [expanded, setExpanded] = useState(defaultOpen);
  const presence = usePresence(expanded, '--app-motion-expand');
  const id = useId();
  return (
    <details
      open={presence.present}
      className={['motion-details', className].filter(Boolean).join(' ')}
    >
      <summary
        aria-expanded={expanded}
        aria-controls={id}
        onClick={(event) => {
          event.preventDefault();
          setExpanded((current) => !current);
        }}
      >
        <ChevronRight aria-hidden="true" className="motion-chevron" />
        <span>{summary}</span>
      </summary>
      <MotionHeight expanded={expanded} id={id}>
        {children}
      </MotionHeight>
    </details>
  );
};

export const MotionMessage = ({
  newMessage,
  ...props
}: HTMLAttributes<HTMLElement> & {newMessage: boolean}) => {
  const animateOnMount = useRef(newMessage);
  return <article {...props} data-motion-new={animateOnMount.current || undefined} />;
};

/** Animate only the measured content height; never transform media or fixed targets. */
export const MotionHeight = ({
  children,
  expanded = true,
  fade = true,
  className = '',
  ...aria
}: PropsWithChildren<{
  expanded?: boolean;
  fade?: boolean;
  className?: string;
  id?: string;
  'aria-busy'?: boolean;
}>) => {
  const {enabled, reduced} = useAppMotion();
  const outer = useRef<HTMLDivElement>(null);
  const inner = useRef<HTMLDivElement>(null);
  const animation = useRef<Animation | null>(null);
  const previous = useRef(0);
  useLayoutEffect(() => {
    if (!outer.current || !inner.current) return;
    const element = outer.current;
    const content = inner.current;
    const update = () => {
      const target = expanded ? content.getBoundingClientRect().height : 0;
      if (target === previous.current && animation.current) return;
      const from = animation.current ? element.getBoundingClientRect().height : previous.current;
      animation.current?.cancel();
      previous.current = target;
      element.style.height = expanded ? 'auto' : '0px';
      if (!enabled || reduced || !element.animate || from === target) {
        element.style.overflow = expanded ? 'visible' : 'hidden';
        return;
      }
      element.style.overflow = 'hidden';
      const running = element.animate(
        [
          {height: from + 'px', ...(fade ? {opacity: expanded ? 0.55 : 1} : {})},
          {height: target + 'px', ...(fade ? {opacity: expanded ? 1 : 0} : {})},
        ],
        {
          duration: readDesignNumber('--app-motion-expand'),
          easing: readDesignToken('--motion-panel-easing'),
        },
      );
      animation.current = running;
      running.onfinish = () => {
        animation.current = null;
        element.style.overflow = expanded ? 'visible' : 'hidden';
      };
    };
    update();
    const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(update) : null;
    observer?.observe(content);
    return () => {
      observer?.disconnect();
      if (animation.current) previous.current = element.getBoundingClientRect().height;
      animation.current?.cancel();
      animation.current = null;
    };
  }, [expanded, fade, enabled, reduced]);
  const style: CSSProperties = {height: expanded ? undefined : 0};
  return (
    <div
      ref={outer}
      className={className}
      style={style}
      aria-hidden={!expanded || undefined}
      inert={!expanded}
      {...aria}
    >
      <div ref={inner} className="motion-height-content">
        {children}
      </div>
    </div>
  );
};
