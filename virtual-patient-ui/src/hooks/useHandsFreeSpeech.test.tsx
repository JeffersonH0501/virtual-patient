import {act, cleanup, renderHook, waitFor} from '@testing-library/react';
import {afterEach, expect, it, vi} from 'vitest';
import {useHandsFreeSpeech} from './useHandsFreeSpeech';
import {SpeechInputCallbacks} from '../speech/SpeechInputProvider';

const provider = vi.hoisted(() => ({callbacks: null as SpeechInputCallbacks | null,
  instances: [] as {start: ReturnType<typeof vi.fn>; pause: ReturnType<typeof vi.fn>}[]}));
vi.mock('../speech', () => ({
  createSpeechInputProvider: (callbacks: SpeechInputCallbacks) => {
    provider.callbacks = callbacks;
    const instance = {
      isSupported: true,
      start: vi.fn(),
      pause: vi.fn(),
      resume: vi.fn(),
      stop: vi.fn(),
      dispose: vi.fn(),
    };
    provider.instances.push(instance);
    return instance;
  },
}));
afterEach(() => {
  cleanup();
  provider.instances = [];
});

it('keeps a replacement microphone provider paused during the opening patient turn', async () => {
  const onUtterance = vi.fn();
  const {rerender} = renderHook(({stream}) => useHandsFreeSpeech({
    language: 'es-ES', paused: true, autoStart: true, microphoneStream: stream, onUtterance,
  }), {initialProps: {stream: null as MediaStream | null}});
  await waitFor(() => expect(provider.instances.at(-1)?.start).toHaveBeenCalled());
  expect(provider.instances.at(-1)?.pause).toHaveBeenCalled();
  rerender({stream: {} as MediaStream});
  const replacement = provider.instances.at(-1)!;
  expect(replacement.start).toHaveBeenCalled();
  expect(replacement.pause).toHaveBeenCalled();
  expect(onUtterance).not.toHaveBeenCalled();
});

it('waits for acceptance and keeps input paused while preparing the patient greeting', async () => {
  const onUtterance = vi.fn();
  const {result, rerender} = renderHook(({accepted}) => useHandsFreeSpeech({
    language: 'es-ES', disabled: !accepted, autoStart: accepted, paused: true, onUtterance,
  }), {initialProps: {accepted: false}});
  expect(result.current.isEnabled).toBe(false);
  expect(provider.instances.every((instance) => instance.start.mock.calls.length === 0)).toBe(true);
  rerender({accepted: true});
  await waitFor(() => expect(result.current.isEnabled).toBe(true));
  expect(provider.instances.at(-1)?.pause).toHaveBeenCalled();
  expect(result.current.isSubmittingUtterance).toBe(false);
  expect(onUtterance).not.toHaveBeenCalled();
});

it('ignores microphone activity and transcripts while the patient has the floor', async () => {
  const onUtterance = vi.fn();
  const onSpeechStart = vi.fn();
  const {result} = renderHook(() => useHandsFreeSpeech({
    language: 'es-ES', paused: true, autoStart: true, onUtterance, onSpeechStart,
  }));
  await waitFor(() => expect(result.current.isEnabled).toBe(true));
  await act(async () => {
    provider.callbacks!.onSpeechStart?.();
    provider.callbacks!.onInterimTranscript('Synthetic greeting echo');
    provider.callbacks!.onUtteranceCaptured?.();
    provider.callbacks!.onFinalTranscript('Synthetic greeting echo');
  });
  expect(onSpeechStart).not.toHaveBeenCalled();
  expect(onUtterance).not.toHaveBeenCalled();
  expect(result.current.hasPendingUtterance).toBe(false);
  expect(result.current.isSubmittingUtterance).toBe(false);
});

it.each(['transcription-empty', 'transcription-failed'])(
  'releases a committed utterance on %s without sending a turn',
  async (error) => {
    const onUtterance = vi.fn();
    const onUtteranceFailed = vi.fn();
    const {result} = renderHook(() =>
      useHandsFreeSpeech({
        language: 'es-ES',
        paused: false,
        autoStart: true,
        onUtterance,
        onUtteranceFailed,
      }),
    );
    await waitFor(() => expect(result.current.isEnabled).toBe(true));
    act(() => provider.callbacks!.onUtteranceCaptured!());
    expect(result.current.isSubmittingUtterance).toBe(true);
    act(() => provider.callbacks!.onError(error));
    expect(result.current.isSubmittingUtterance).toBe(false);
    expect(result.current.hasPendingUtterance).toBe(false);
    expect(onUtteranceFailed).toHaveBeenCalledOnce();
    expect(onUtterance).not.toHaveBeenCalled();
    expect(result.current.errorCode).toBe(error);
    act(() => provider.callbacks!.onUtteranceCaptured!());
    expect(result.current.errorCode).toBeNull();
  },
);

it('keeps submission pending until accepted conversation work settles', async () => {
  let finish!: () => void;
  const onUtterance = vi.fn(
    () =>
      new Promise<void>((resolve) => {
        finish = resolve;
      }),
  );
  const {result} = renderHook(() =>
    useHandsFreeSpeech({language: 'en-US', paused: false, autoStart: true, onUtterance}),
  );
  await waitFor(() => expect(result.current.isEnabled).toBe(true));
  await act(async () => {
    provider.callbacks!.onUtteranceCaptured!();
    provider.callbacks!.onFinalTranscript('Synthetic text');
  });
  expect(result.current.isSubmittingUtterance).toBe(true);
  await act(async () => finish());
  expect(result.current.isSubmittingUtterance).toBe(false);
});
