import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import {useHandsFreeSpeech} from './useHandsFreeSpeech';
import {SpeechInputCallbacks} from '../speech/SpeechInputProvider';

const provider = vi.hoisted(() => ({
  callbacks: null as SpeechInputCallbacks | null,
  instances: [] as {start: ReturnType<typeof vi.fn>; stop: ReturnType<typeof vi.fn>}[],
}));

// A class is used on purpose: the hook creates the provider with `new`.
vi.mock('../speech/ServerSpeechTranscriptionProvider', () => ({
  ServerSpeechTranscriptionProvider: class {
    isSupported = true;
    start = vi.fn();
    pause = vi.fn();
    resume = vi.fn();
    stop = vi.fn();
    dispose = vi.fn();
    constructor(callbacks: SpeechInputCallbacks) {
      provider.callbacks = callbacks;
      provider.instances.push(this);
    }
  },
}));

afterEach(() => {
  cleanup();
  provider.instances = [];
});

const options = {language: 'es-ES', autoStart: true, paused: false, microphoneStream: {} as MediaStream, onUtterance: vi.fn()};

it('listens again after an explicit stop, so the voice bubble returns when the closing dialog is cancelled', async () => {
  const {result} = renderHook(() => useHandsFreeSpeech(options));
  await waitFor(() => expect(result.current.isEnabled).toBe(true));
  const first = provider.instances.at(-1)!;
  expect(first.start).toHaveBeenCalled();

  // Opening the closing dialog stops recognition.
  act(() => result.current.stop());
  await waitFor(() => expect(result.current.isEnabled).toBe(false));
  expect(first.stop).toHaveBeenCalled();

  // Cancelling reopens the capture; start() turns recognition back on with a new provider.
  act(() => result.current.start());
  await waitFor(() => expect(result.current.isEnabled).toBe(true));
  const restarted = provider.instances.at(-1)!;
  expect(restarted).not.toBe(first);
  expect(restarted.start).toHaveBeenCalled();

  // Interim speech is shown again (the bubble).
  act(() => provider.callbacks!.onInterimTranscript('hola doctora'));
  expect(result.current.interimTranscript).toBe('hola doctora');
  expect(result.current.hasPendingUtterance).toBe(true);
});

it('does not start recognition while the hook is disabled', async () => {
  const {result} = renderHook(() => useHandsFreeSpeech({...options, autoStart: false, disabled: true}));
  act(() => result.current.start());
  expect(provider.instances.every((instance) => instance.start.mock.calls.length === 0)).toBe(true);
});
it('starts recognition once the hook is no longer disabled after start() was requested', async () => {
  const {result, rerender} = renderHook(({disabled}) => useHandsFreeSpeech({...options, autoStart: false, disabled}), {initialProps: {disabled: true}});
  act(() => result.current.start());
  rerender({disabled: false});
  await waitFor(() => expect(provider.instances.at(-1)!.start).toHaveBeenCalled());
});
