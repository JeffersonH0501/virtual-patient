import {act, cleanup, renderHook} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import {usePatientAudioRoute} from './usePatientAudioRoute';

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

it('keeps the native player output on an iPad reporting a desktop user agent', async () => {
  vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue('Mozilla/5.0 (Macintosh)');
  vi.stubGlobal('navigator', Object.create(navigator, {maxTouchPoints: {value: 5}, userAgent: {value: navigator.userAgent}}));
  const graph = {state: 'running', createMediaElementSource: vi.fn(), close: vi.fn(async () => undefined)};
  const AudioContext = vi.fn(function () { return graph; });
  vi.stubGlobal('AudioContext', AudioContext);
  const {result} = renderHook(usePatientAudioRoute);
  await act(async () => result.current.resumeAudioGraph());
  expect(AudioContext).not.toHaveBeenCalled();
  expect(result.current.routePatientAudio(document.createElement('audio'))).toBe(false);
});

it('keeps the patient output connected across pauses and releases it when playback ends', async () => {
  vi.useFakeTimers();
  const node = () => ({connect: vi.fn(), disconnect: vi.fn()});
  const source = node();
  const analyser = {...node(), fftSize: 0, getFloatTimeDomainData: vi.fn((samples: Float32Array) => samples.fill(.1))};
  const graph = {
    state: 'running', destination: {},
    resume: vi.fn(async () => { graph.state = 'running'; }),
    close: vi.fn(async () => undefined),
    createMediaElementSource: vi.fn(() => source),
    createAnalyser: () => analyser,
    createGain: () => ({...node(), gain: {value: 0}}),
    createDynamicsCompressor: () => ({...node(), threshold: {value: 0}, knee: {value: 0},
      ratio: {value: 0}, attack: {value: 0}, release: {value: 0}}),
  };
  vi.stubGlobal('AudioContext', class { constructor() { return graph; } });
  const {result, unmount} = renderHook(() => usePatientAudioRoute());
  const player = {paused: true, ended: false} as HTMLAudioElement;
  await act(async () => result.current.resumeAudioGraph());
  act(() => { expect(result.current.routePatientAudio(player)).toBe(true); });
  // Routing can precede play(), and later capture pauses reuse the same player.
  act(() => vi.advanceTimersByTime(120));
  expect(source.disconnect).not.toHaveBeenCalled();
  player.paused = false;
  act(() => vi.advanceTimersByTime(60));
  expect(result.current.patientAudioLevel).toBeGreaterThan(0);
  player.paused = true;
  act(() => vi.advanceTimersByTime(120));
  expect(result.current.patientAudioLevel).toBe(0);
  expect(source.disconnect).not.toHaveBeenCalled();
  graph.state = 'suspended';
  await act(async () => result.current.resumeAudioGraph());
  player.paused = false;
  act(() => vi.advanceTimersByTime(60));
  expect(result.current.patientAudioLevel).toBeGreaterThan(0);
  expect(source.connect).toHaveBeenCalledOnce();
  expect(source.disconnect).not.toHaveBeenCalled();
  player.ended = true;
  act(() => vi.advanceTimersByTime(60));
  expect(source.disconnect).toHaveBeenCalledOnce();
  expect(analyser.disconnect).toHaveBeenCalledOnce();
  expect(result.current.patientAudioLevel).toBe(0);
  act(() => { result.current.routePatientAudio({paused: false, ended: false} as HTMLAudioElement); });
  unmount();
  expect(source.disconnect).toHaveBeenCalledTimes(2);
  expect(graph.close).toHaveBeenCalledOnce();
});
