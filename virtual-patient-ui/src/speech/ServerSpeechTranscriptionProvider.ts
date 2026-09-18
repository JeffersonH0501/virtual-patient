import {transcribeStudentAudio} from '../services/speech/transcribeStudentAudio';
import {SpeechInputCallbacks, SpeechInputProvider} from './SpeechInputProvider';
import {selectAudioMimeType} from '../utils/mediaRecorder';

const ANALYSIS_INTERVAL_MS = 50;
const MINIMUM_SPEECH_MS = 250;
const MINIMUM_ACTIVITY_RMS = 0.012;
const NOISE_MULTIPLIER = 2.5;

const extensionFor = (mimeType: string): string =>
  mimeType.includes('mp4') ? 'm4a' : 'webm';

type SegmentRecorder = MediaRecorder & {
  transcriptionMetadata?: {
    transcribe: boolean;
    startedAt: number;
    endedAt: number;
  };
};

export class ServerSpeechTranscriptionProvider implements SpeechInputProvider {
  readonly isSupported = Boolean(
    typeof navigator.mediaDevices?.getUserMedia === 'function'
      && typeof MediaRecorder !== 'undefined'
      && typeof AudioContext !== 'undefined',
  );

  private stream: MediaStream | null = null;
  private audioContext: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private analysisTimer: number | null = null;
  private recorder: MediaRecorder | null = null;
  private active = false;
  private paused = false;
  private starting = false;
  private language = 'en-US';
  private noiseFloor = 0.004;
  private speechStartedAt: number | null = null;
  private transcriptionQueue = Promise.resolve();
  private inputGeneration = 0;
  private captureGeneration = 0;

  constructor(
    private readonly callbacks: SpeechInputCallbacks,
    private readonly sharedStream: MediaStream | null = null,
  ) {}

  start(language: string): void {
    if (!this.isSupported) {
      this.callbacks.onError('unsupported');
      return;
    }
    this.language = language;
    this.active = true;
    this.paused = false;
    this.callbacks.onError(null);
    void this.ensureCapture();
  }

  pause(): void {
    if (!this.active || this.paused) return;
    this.paused = true;
    this.inputGeneration += 1;
    this.stopAnalysis();
    this.finishSegment(false);
    this.callbacks.onInterimTranscript('');
    this.callbacks.onAudioLevel?.(0);
    this.callbacks.onStateChange('paused');
  }

  resume(): void {
    if (!this.active || !this.paused) return;
    this.paused = false;
    this.callbacks.onError(null);
    void this.ensureCapture();
  }

  submitUtterance(): void {
    if (!this.active || this.paused || !this.hasUsableSpeech()) return;
    this.finishSegment(true);
    this.callbacks.onInterimTranscript('');
    this.callbacks.onAudioLevel?.(0);
  }

  stop(): void {
    this.active = false;
    this.captureGeneration += 1;
    this.paused = false;
    this.inputGeneration += 1;
    this.stopAnalysis();
    this.finishSegment(this.hasUsableSpeech());
    this.releaseCapture();
    this.callbacks.onInterimTranscript('');
    this.callbacks.onAudioLevel?.(0);
    this.callbacks.onStateChange('idle');
  }

  dispose(): void {
    this.stop();
  }

  private async ensureCapture(): Promise<void> {
    if (this.starting || !this.active || this.paused) return;
    this.starting = true;
    const generation = this.captureGeneration;
    try {
      if (!this.stream) {
        const stream = this.sharedStream ?? await navigator.mediaDevices.getUserMedia({
          audio: {echoCancellation: true, noiseSuppression: true, autoGainControl: true},
        });
        if (!this.active || generation !== this.captureGeneration) {
          if (!this.sharedStream) stream.getTracks().forEach((track) => track.stop());
          return;
        }
        this.stream = stream;
        const AudioContextConstructor = window.AudioContext;
        if (!AudioContextConstructor) throw new Error('AudioContext is unavailable');
        this.audioContext = new AudioContextConstructor();
        const source = this.audioContext.createMediaStreamSource(this.stream);
        this.analyser = this.audioContext.createAnalyser();
        this.analyser.fftSize = 2048;
        source.connect(this.analyser);
      }
      await this.audioContext?.resume();
      if (!this.active || this.paused || generation !== this.captureGeneration) return;
      this.startSegment();
      this.startAnalysis();
      this.callbacks.onStateChange('listening');
    } catch (error) {
      if (generation !== this.captureGeneration) return;
      const code = error instanceof DOMException && error.name === 'NotAllowedError'
        ? 'not-allowed'
        : 'audio-capture';
      this.active = false;
      this.callbacks.onError(code);
      this.callbacks.onStateChange('idle');
      this.releaseCapture();
    } finally {
      this.starting = false;
      if (this.active && !this.paused && generation !== this.captureGeneration) {
        void this.ensureCapture();
      }
    }
  }

  private startSegment(): void {
    if (!this.stream || this.recorder || !this.active || this.paused) return;
    const mimeType = selectAudioMimeType();
    if (!mimeType) {
      this.callbacks.onError('unsupported-codec');
      return;
    }
    const chunks: Blob[] = [];
    const recorder = new MediaRecorder(this.stream, {mimeType}) as SegmentRecorder;
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data);
    };
    recorder.onstop = () => {
      const metadata = recorder.transcriptionMetadata;
      const shouldTranscribe = metadata?.transcribe ?? false;
      const startedAt = metadata?.startedAt ?? performance.now();
      const endedAt = metadata?.endedAt ?? performance.now();
      if (shouldTranscribe && chunks.length > 0) {
        const audio = new Blob(chunks, {type: mimeType});
        this.enqueueTranscription(audio, mimeType, startedAt, endedAt, true);
      }
      if (this.active && !this.paused) this.startSegment();
    };
    this.recorder = recorder;
    recorder.start();
  }

  private startAnalysis(): void {
    this.stopAnalysis();
    this.analysisTimer = window.setInterval(() => this.analyseAudio(), ANALYSIS_INTERVAL_MS);
  }

  private analyseAudio(): void {
    if (!this.analyser || !this.active || this.paused) return;
    const samples = new Float32Array(this.analyser.fftSize);
    this.analyser.getFloatTimeDomainData(samples);
    const rms = Math.sqrt(samples.reduce((sum, sample) => sum + sample * sample, 0) / samples.length);
    this.callbacks.onAudioLevel?.(Math.min(1, rms / 0.12));
    const threshold = Math.max(MINIMUM_ACTIVITY_RMS, this.noiseFloor * NOISE_MULTIPLIER);
    const now = performance.now();
    if (rms >= threshold) {
      if (this.speechStartedAt === null) {
        this.speechStartedAt = now;
        this.callbacks.onSpeechStart?.();
        this.callbacks.onInterimTranscript('…');
      }
      return;
    }
    if (this.speechStartedAt === null) {
      this.noiseFloor = this.noiseFloor * 0.95 + rms * 0.05;
      return;
    }
  }

  private hasUsableSpeech(): boolean {
    return this.speechStartedAt !== null
      && performance.now() - this.speechStartedAt >= MINIMUM_SPEECH_MS;
  }

  private finishSegment(shouldTranscribe: boolean, endedAt = performance.now()): void {
    const recorder = this.recorder;
    this.recorder = null;
    const startedAt = this.speechStartedAt ?? endedAt;
    this.speechStartedAt = null;
    if (!recorder || recorder.state === 'inactive') return;
    (recorder as SegmentRecorder).transcriptionMetadata = {
      transcribe: shouldTranscribe,
      startedAt,
      endedAt,
    };
    if (shouldTranscribe) this.callbacks.onUtteranceCaptured?.();
    recorder.stop();
  }

  private enqueueTranscription(
    audio: Blob,
    mimeType: string,
    startedAt: number,
    endedAt: number,
    committedByStudent: boolean,
  ): void {
    const language = this.language.toLowerCase().startsWith('es') ? 'es' : 'en';
    const filename = `student-utterance.${extensionFor(mimeType)}`;
    const generation = this.inputGeneration;
    this.transcriptionQueue = this.transcriptionQueue
      .then(async () => {
        const result = await transcribeStudentAudio(audio, filename, language);
        if (
          !this.active
          || (!committedByStudent && (this.paused || generation !== this.inputGeneration))
        ) return;
        const text = result.text.trim();
        if (text) {
          this.callbacks.onFinalTranscript(text, {
            startedAt,
            endedAt,
            inputSource: 'azure_openai_stt',
            timingSource: 'client_audio_activity',
          });
        }
      })
      .catch(() => this.callbacks.onError('transcription-failed'));
  }

  private stopAnalysis(): void {
    if (this.analysisTimer === null) return;
    window.clearInterval(this.analysisTimer);
    this.analysisTimer = null;
  }

  private releaseCapture(): void {
    if (!this.sharedStream) this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    void this.audioContext?.close();
    this.audioContext = null;
    this.analyser = null;
  }
}
