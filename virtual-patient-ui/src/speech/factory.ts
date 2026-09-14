import {BrowserSpeechRecognitionProvider} from './BrowserSpeechRecognitionProvider';
import {ServerSpeechTranscriptionProvider} from './ServerSpeechTranscriptionProvider';
import {SpeechInputCallbacks, SpeechInputProvider} from './SpeechInputProvider';

export const createSpeechInputProvider = (
  callbacks: SpeechInputCallbacks,
  microphoneStream?: MediaStream | null,
): SpeechInputProvider => {
  const providerName = import.meta.env.VITE_SPEECH_INPUT_PROVIDER || 'browser';
  if (providerName === 'browser') {
    return new BrowserSpeechRecognitionProvider(callbacks);
  }
  if (providerName === 'server') {
    return new ServerSpeechTranscriptionProvider(callbacks, microphoneStream);
  }
  throw new Error(`Unsupported speech input provider: ${providerName}`);
};
