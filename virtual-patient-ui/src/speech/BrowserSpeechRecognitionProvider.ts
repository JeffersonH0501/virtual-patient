import {
  SpeechInputCallbacks,
  SpeechInputProvider,
} from './SpeechInputProvider';

type SpeechRecognitionAlternativeLike = {
  transcript: string;
};

type SpeechRecognitionResultLike = {
  isFinal: boolean;
  [index: number]: SpeechRecognitionAlternativeLike;
};

type SpeechRecognitionEventLike = {
  resultIndex: number;
  results: {
    length: number;
    [index: number]: SpeechRecognitionResultLike;
  };
};

type SpeechRecognitionErrorEventLike = {
  error: string;
};

type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  onstart: (() => void) | null;
  onend: (() => void) | null;
  onresult: ((event: SpeechRecognitionEventLike) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEventLike) => void) | null;
  onspeechstart: (() => void) | null;
  onspeechend: (() => void) | null;
  start(): void;
  abort(): void;
};

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}

export class BrowserSpeechRecognitionProvider implements SpeechInputProvider {
  readonly isSupported: boolean;

  private recognition: SpeechRecognitionLike | null = null;
  private active = false;
  private paused = false;
  private language = 'en-US';
  private restartTimer: number | null = null;
  private networkRetryCount = 0;
  private speechStartedAt: number | null = null;
  private speechEndedAt: number | null = null;

  constructor(private readonly callbacks: SpeechInputCallbacks) {
    const Constructor = window.SpeechRecognition ?? window.webkitSpeechRecognition;
    this.isSupported = Boolean(Constructor);
    if (!Constructor) return;

    this.recognition = new Constructor();
    this.recognition.continuous = true;
    this.recognition.interimResults = true;
    this.recognition.maxAlternatives = 1;
    this.recognition.onstart = () => this.callbacks.onStateChange('listening');
    this.recognition.onresult = (event) => this.handleResult(event);
    this.recognition.onerror = (event) => this.handleError(event.error);
    this.recognition.onend = () => this.handleEnd();
    this.recognition.onspeechstart = () => {
      this.speechStartedAt = performance.now();
      this.speechEndedAt = null;
    };
    this.recognition.onspeechend = () => {
      this.speechEndedAt = performance.now();
    };
  }

  start(language: string): void {
    if (!this.recognition || !this.isSupported) {
      this.callbacks.onError('unsupported');
      return;
    }
    this.language = language;
    this.recognition.lang = language;
    this.active = true;
    this.paused = false;
    this.networkRetryCount = 0;
    this.callbacks.onError(null);
    this.safeStart();
  }

  pause(): void {
    if (!this.recognition || !this.active || this.paused) return;
    this.paused = true;
    this.clearRestartTimer();
    this.recognition.abort();
    this.callbacks.onStateChange('paused');
    this.callbacks.onInterimTranscript('');
  }

  resume(): void {
    if (!this.recognition || !this.active || !this.paused) return;
    this.paused = false;
    this.recognition.lang = this.language;
    this.callbacks.onError(null);
    this.safeStart();
  }

  submitUtterance(): void {
    if (!this.active || this.paused) return;
    this.callbacks.onUtteranceCaptured?.();
  }

  stop(): void {
    if (!this.recognition) return;
    this.active = false;
    this.paused = false;
    this.clearRestartTimer();
    this.recognition.abort();
    this.callbacks.onInterimTranscript('');
    this.callbacks.onStateChange('idle');
  }

  dispose(): void {
    this.stop();
    if (!this.recognition) return;
    this.recognition.onstart = null;
    this.recognition.onend = null;
    this.recognition.onresult = null;
    this.recognition.onerror = null;
    this.recognition.onspeechstart = null;
    this.recognition.onspeechend = null;
    this.recognition = null;
  }

  private safeStart(): void {
    if (!this.recognition || !this.active || this.paused) return;
    try {
      this.recognition.start();
    } catch (error) {
      if (!(error instanceof DOMException && error.name === 'InvalidStateError')) {
        this.callbacks.onError('start-failed');
      }
    }
  }

  private handleResult(event: SpeechRecognitionEventLike): void {
    this.networkRetryCount = 0;
    this.callbacks.onError(null);
    let interimTranscript = '';
    const finalSegments: string[] = [];
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const result = event.results[index];
      const transcript = result[0]?.transcript.trim() ?? '';
      if (!transcript) continue;
      if (result.isFinal) finalSegments.push(transcript);
      else interimTranscript += `${transcript} `;
    }
    this.callbacks.onInterimTranscript(interimTranscript.trim());
    if (finalSegments.length > 0) {
      const now = performance.now();
      this.callbacks.onUtteranceCaptured?.();
      this.callbacks.onFinalTranscript(finalSegments.join(' '), {
        startedAt: this.speechStartedAt ?? now,
        endedAt: this.speechEndedAt ?? now,
        inputSource: 'browser_speech',
        timingSource: 'browser_speech_events',
      });
      this.speechStartedAt = null;
      this.speechEndedAt = null;
    }
  }

  private handleError(errorCode: string): void {
    if (errorCode === 'aborted' || errorCode === 'no-speech') return;
    if (
      errorCode === 'not-allowed' ||
      errorCode === 'service-not-allowed' ||
      errorCode === 'audio-capture'
    ) {
      this.active = false;
    }
    if (errorCode === 'network') {
      this.networkRetryCount += 1;
      this.callbacks.onError(navigator.onLine ? 'network' : 'offline');
      return;
    }
    this.callbacks.onError(errorCode);
  }

  private handleEnd(): void {
    if (!this.active) {
      this.callbacks.onStateChange('idle');
      return;
    }
    if (this.paused) {
      this.callbacks.onStateChange('paused');
      return;
    }
    const retryDelay =
      this.networkRetryCount > 0
        ? Math.min(1000 * 2 ** (this.networkRetryCount - 1), 8000)
        : 250;
    this.clearRestartTimer();
    this.restartTimer = window.setTimeout(() => {
      this.restartTimer = null;
      this.safeStart();
    }, retryDelay);
  }

  private clearRestartTimer(): void {
    if (this.restartTimer === null) return;
    window.clearTimeout(this.restartTimer);
    this.restartTimer = null;
  }
}
