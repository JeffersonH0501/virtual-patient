/** Read CSS design values needed by browser APIs that cannot consume CSS directly. */
export const readDesignToken = (name: string): string =>
  typeof document === 'undefined'
    ? ''
    : getComputedStyle(document.documentElement).getPropertyValue(name).trim();

/** Unitless CSS values are used for JavaScript timers and canvas coordinates. */
export const readDesignNumber = (name: string): number =>
  Number.parseFloat(readDesignToken(name)) || 0;

/**
 * A CSS time token in milliseconds, accepting either unit. The production build
 * minifies `320ms` to `.32s`, so a plain parseFloat would read `0.32` and make
 * Web Animations / timers run ~instantly. Convert `s` values to milliseconds.
 */
export const readDesignDuration = (name: string): number => {
  const value = readDesignToken(name);
  const amount = Number.parseFloat(value) || 0;
  return /\d\s*s$/.test(value) && !/ms$/.test(value) ? amount * 1000 : amount;
};
