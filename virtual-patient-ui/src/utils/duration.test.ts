import {expect, it} from 'vitest';
import {formatDuration} from './duration';

it('keeps missing duration distinct from a confirmed zero duration', () => {
  expect(formatDuration(null)).toBe('—');
  expect(formatDuration(Number.NaN)).toBe('—');
  expect(formatDuration(0)).toBe('0s');
  expect(formatDuration(51)).toBe('51s');
  expect(formatDuration(60)).toBe('1m');
  expect(formatDuration(121)).toBe('2m 1s');
  expect(formatDuration(3600)).toBe('1h');
  expect(formatDuration(3725)).toBe('1h 2m 5s');
});
