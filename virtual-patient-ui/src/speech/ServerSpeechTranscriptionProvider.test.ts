/* eslint-disable max-classes-per-file */
import {afterEach, beforeEach, describe, expect, it, vi} from 'vitest';
import {ServerSpeechTranscriptionProvider} from './ServerSpeechTranscriptionProvider';
import {transcribeStudentAudio} from '../services/speech/transcribeStudentAudio';

vi.mock('../services/speech/transcribeStudentAudio', () => ({transcribeStudentAudio: vi.fn()}));

class Recorder {
  static empty = false;
  static isTypeSupported() {
    return true;
  }
  state = 'inactive';
  ondataavailable?: (event: {data: Blob}) => void;
  onstop?: () => void;
  start() {
    this.state = 'recording';
  }
  stop() {
    this.state = 'inactive';
    this.ondataavailable?.({data: new Blob(Recorder.empty ? [] : ['synthetic'])});
    this.onstop?.();
  }
}

class AudioContext {
  createMediaStreamSource() {
    return {connect: vi.fn()};
  }
  createAnalyser() {
    return {fftSize: 2048, getFloatTimeDomainData: vi.fn()};
  }
  resume = vi.fn().mockResolvedValue(undefined);
  close = vi.fn().mockResolvedValue(undefined);
}

const settle = async () => {
  for (let i = 0; i < 10; i += 1) await Promise.resolve();
};

describe('server speech segment completion', () => {
  let provider: ServerSpeechTranscriptionProvider;
  let callbacks: {onError: ReturnType<typeof vi.fn>; onFinalTranscript: ReturnType<typeof vi.fn>};

  beforeEach(async () => {
    vi.stubGlobal('MediaRecorder', Recorder);
    vi.stubGlobal('AudioContext', AudioContext);
    Object.defineProperty(navigator, 'mediaDevices', {
      configurable: true,
      value: {getUserMedia: vi.fn()},
    });
    Recorder.empty = false;
    vi.mocked(transcribeStudentAudio).mockReset();
    callbacks = {onError: vi.fn(), onFinalTranscript: vi.fn()};
    provider = new ServerSpeechTranscriptionProvider(
      {
        ...callbacks,
        onInterimTranscript: vi.fn(),
        onStateChange: vi.fn(),
        onUtteranceCaptured: () => provider.pause(),
      },
      {active: true} as MediaStream,
    );
    provider.start('es-ES');
    await settle();
    callbacks.onError.mockClear();
  });

  afterEach(() => {
    provider.dispose();
    vi.unstubAllGlobals();
  });

  const submit = () => {
    provider['speechStartedAt'] = performance.now() - 300;
    provider.submitUtterance();
  };

  it.each(['', '   \n'])(
    'reports empty transcription as recoverable without inventing a turn (%j)',
    async (text) => {
      vi.mocked(transcribeStudentAudio).mockResolvedValue({text});
      submit();
      await settle();
      expect(callbacks.onError).toHaveBeenCalledWith('transcription-empty');
      expect(callbacks.onFinalTranscript).not.toHaveBeenCalled();
    },
  );

  it('delivers committed text during the patient-floor pause with original speech timing', async () => {
    vi.mocked(transcribeStudentAudio).mockResolvedValue({text: '  Hola  '});
    submit();
    await settle();
    expect(callbacks.onFinalTranscript).toHaveBeenCalledWith(
      'Hola',
      expect.objectContaining({
        inputSource: 'azure_openai_stt',
        timingSource: 'client_audio_activity',
      }),
    );
  });

  it('keeps the failure notice on resume and accepts the next spoken turn', async () => {
    vi.mocked(transcribeStudentAudio)
      .mockRejectedValueOnce(new Error('Synthetic network failure'))
      .mockResolvedValueOnce({text: 'Hola'});
    submit();
    await settle();
    expect(callbacks.onError).toHaveBeenLastCalledWith('transcription-failed');

    provider.resume();
    await settle();
    expect(callbacks.onError).toHaveBeenLastCalledWith('transcription-failed');

    submit();
    await settle();
    expect(callbacks.onFinalTranscript).toHaveBeenCalledExactlyOnceWith('Hola', expect.any(Object));
  });

  it('reports a committed segment with no encoded chunks instead of hanging', async () => {
    Recorder.empty = true;
    submit();
    await settle();
    expect(callbacks.onError).toHaveBeenCalledWith('transcription-empty');
    expect(transcribeStudentAudio).not.toHaveBeenCalled();
  });

  it('cancels an unsubmitted phrase without claiming a new committed utterance', async () => {
    const committed = vi.spyOn(provider['callbacks'], 'onUtteranceCaptured');
    provider['speechStartedAt'] = performance.now() - 300;
    provider.stop();
    await settle();
    expect(committed).not.toHaveBeenCalled();
    expect(transcribeStudentAudio).not.toHaveBeenCalled();
  });

  it.each(['resolve', 'reject'])(
    'ignores a stale STT %s after stop and restart',
    async (outcome) => {
      let resolve!: (value: {text: string}) => void;
      let reject!: (error: Error) => void;
      vi.mocked(transcribeStudentAudio).mockReturnValue(
        new Promise((yes, no) => {
          resolve = yes;
          reject = no;
        }),
      );
      submit();
      await settle();
      provider.stop();
      provider.start('es-ES');
      await settle();
      callbacks.onError.mockClear();
      if (outcome === 'resolve') resolve({text: 'Stale synthetic text'});
      else reject(new Error('Stale synthetic failure'));
      await settle();
      expect(callbacks.onFinalTranscript).not.toHaveBeenCalled();
      expect(callbacks.onError).not.toHaveBeenCalled();
    },
  );
});
