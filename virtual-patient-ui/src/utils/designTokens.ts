/** Read CSS design values needed by browser APIs that cannot consume CSS directly. */
export const readDesignToken = (name: string): string =>
  typeof document === 'undefined'
    ? ''
    : getComputedStyle(document.documentElement).getPropertyValue(name).trim();

/** Unitless CSS values are used for JavaScript timers and canvas coordinates. */
export const readDesignNumber = (name: string): number =>
  Number.parseFloat(readDesignToken(name)) || 0;
