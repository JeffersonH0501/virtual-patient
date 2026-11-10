import {describe, expect, it} from 'vitest';
import {sessionElapsedAt} from './sessionClock';

describe('session event clock', () => {
  it('keeps historical events stable after later pauses', () => {
    expect(sessionElapsedAt(1000, 0, [{start: 2000, end: 4000}])).toBe(1000);
    expect(sessionElapsedAt(5000, 0, [{start: 2000, end: 4000}])).toBe(3000);
  });
  it('clips events during an active or completed pause', () => {
    expect(sessionElapsedAt(3000, 0, [{start: 2000, end: null}])).toBe(2000);
    expect(sessionElapsedAt(3000, 0, [{start: 2000, end: 4000}])).toBe(2000);
  });
});
