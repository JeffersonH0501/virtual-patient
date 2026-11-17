import {afterEach, expect, it, vi} from 'vitest';
import {readDesignDuration, readDesignNumber} from './designTokens';

const withToken = (value: string) =>
  vi.spyOn(window, 'getComputedStyle').mockReturnValue({
    getPropertyValue: () => value,
  } as unknown as CSSStyleDeclaration);

afterEach(() => vi.restoreAllMocks());

it('reads a duration in milliseconds whether CSS uses ms or the minified s form', () => {
  // The production build minifies 320ms to .32s; both must yield 320 ms.
  withToken('320ms');
  expect(readDesignDuration('--app-motion-enter')).toBe(320);
  withToken('.32s');
  expect(readDesignDuration('--app-motion-enter')).toBe(320);
  withToken('35ms');
  expect(readDesignDuration('--app-motion-stagger')).toBe(35);
  withToken('.035s');
  expect(readDesignDuration('--app-motion-stagger')).toBe(35);
});

it('falls back to zero for an empty or unitless token', () => {
  withToken('');
  expect(readDesignDuration('--missing')).toBe(0);
  // A plain unitless number (e.g. a frame count) is read as-is.
  withToken('150');
  expect(readDesignDuration('--motion-modal-unmount-long')).toBe(150);
});

it('readDesignNumber still reads pixel tokens unchanged', () => {
  withToken('12px');
  expect(readDesignNumber('--layout-inset')).toBe(12);
});
