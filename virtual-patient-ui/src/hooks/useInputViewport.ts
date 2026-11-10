import {useEffect} from 'react';

const textInputTypes = new Set(['text', 'search', 'email', 'password', 'tel', 'url', 'number']);

/** Keep the shared layout and focused text field inside the keyboard-adjusted viewport. */
export const useInputViewport = () => {
  useEffect(() => {
    const root = document.documentElement;
    const viewport = window.visualViewport;
    let frame = 0;
    let reveal = false;
    const update = () => {
      frame = 0;
      const shouldReveal = reveal;
      reveal = false;
      // Pinch zoom must retain native panning rather than reflow the application.
      if (viewport && Math.abs(viewport.scale - 1) > 0.01) return;
      const height = viewport?.height ?? window.innerHeight;
      const top = viewport?.offsetTop ?? 0;
      if (height <= 0) return;
      root.style.setProperty('--app-viewport-height', `${height}px`);
      root.style.setProperty('--app-viewport-top', `${top}px`);
      if (!shouldReveal) return;
      const field = document.activeElement;
      if (!(field instanceof HTMLTextAreaElement || field instanceof HTMLInputElement && textInputTypes.has(field.type)) ||
          field.disabled || field.readOnly || field.closest('[hidden], [inert], [aria-hidden="true"]')) return;
      let visibleTop = top;
      let visibleBottom = top + height;
      for (let parent = field.parentElement; parent; parent = parent.parentElement) {
        if (!/(auto|scroll)/.test(getComputedStyle(parent).overflowY)) continue;
        const bounds = parent.getBoundingClientRect();
        visibleTop = Math.max(visibleTop, bounds.top);
        visibleBottom = Math.min(visibleBottom, bounds.bottom);
      }
      const bounds = field.getBoundingClientRect();
      if (bounds.top < visibleTop || bounds.bottom > visibleBottom) {
        field.scrollIntoView?.({block: 'nearest', inline: 'nearest', behavior: 'instant'});
      }
    };
    const schedule = (revealField: boolean) => {
      reveal ||= revealField;
      if (!frame) frame = window.requestAnimationFrame(update);
    };
    const revealField = () => schedule(true);
    const followViewport = () => schedule(false);
    window.addEventListener('resize', revealField);
    viewport?.addEventListener('resize', revealField);
    viewport?.addEventListener('scroll', followViewport);
    document.addEventListener('focusin', revealField);
    document.addEventListener('input', revealField);
    schedule(true);
    return () => {
      window.cancelAnimationFrame(frame);
      window.removeEventListener('resize', revealField);
      viewport?.removeEventListener('resize', revealField);
      viewport?.removeEventListener('scroll', followViewport);
      document.removeEventListener('focusin', revealField);
      document.removeEventListener('input', revealField);
      root.style.removeProperty('--app-viewport-height');
      root.style.removeProperty('--app-viewport-top');
    };
  }, []);
};
