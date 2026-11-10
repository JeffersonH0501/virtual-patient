import {cleanup, render} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import {VoiceWave} from './VoiceWave';

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it('uses one frame clock and moves on physical pixels across sample boundaries', () => {
  let frame: FrameRequestCallback = () => undefined;
  const request = vi.fn((callback: FrameRequestCallback) => {
    frame = callback;
    return 1;
  });
  const cancel = vi.fn();
  vi.stubGlobal('requestAnimationFrame', request);
  vi.stubGlobal('cancelAnimationFrame', cancel);
  vi.stubGlobal('devicePixelRatio', 1.25);
  vi.spyOn(performance, 'now').mockReturnValue(0);
  vi.stubGlobal('getComputedStyle', () => ({
    getPropertyValue: (name: string) => name === '--wave-bar-width' ? '3px' : '2px',
  }));
  const view = render(<VoiceWave level={0.7} active speaker="student" />);
  const track = view.container.querySelector('.voice-wave-track') as HTMLElement;
  for (const time of [16, 33, 50, 99, 100, 116]) {
    frame(time);
    const offset = Number(track.style.transform.match(/-?[\d.]+/)?.[0]);
    expect(Number.isInteger(offset * 1.25)).toBe(true);
  }
  expect((track.lastElementChild as HTMLElement).style.getPropertyValue('--wave-level')).toBe('0.7');
  expect(track.children).toHaveLength(80);
  expect(Number.parseFloat(track.style.getPropertyValue('--wave-bar-width')) * 1.25).toBe(4);
  expect(Number.parseFloat(track.style.getPropertyValue('--wave-bar-gap')) * 1.25).toBe(3);
  const pending = request.mock.calls.length;
  view.rerender(<VoiceWave level={0.4} active speaker="student" />);
  expect(request).toHaveBeenCalledTimes(pending);
  frame(200);
  expect((track.lastElementChild as HTMLElement).style.getPropertyValue('--wave-level')).toBe('0.4');
  view.unmount();
  expect(cancel).toHaveBeenCalled();
});
