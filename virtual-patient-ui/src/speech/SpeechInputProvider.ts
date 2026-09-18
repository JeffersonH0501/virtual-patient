import {SpeechTiming} from '../types/recording';

export type SpeechInputState = 'idle' | 'listening' | 'paused';

export type SpeechInputCallbacks = {
  onInterimTranscript: (text: string) => void;
  onUtteranceCaptured?: () => void;
  onSpeechStart?: () => void;
  onFinalTranscript: (text: string, timing?: SpeechTiming) => void;
  onStateChange: (state: SpeechInputState) => void;
  onError: (errorCode: string | null) => void;
  onAudioLevel?: (level: number) => void;
};

export interface SpeechInputProvider {
  readonly isSupported: boolean;
  start(language: string): void;
  pause(): void;
  resume(): void;
  submitUtterance(): void;
  stop(): void;
  dispose(): void;
}
