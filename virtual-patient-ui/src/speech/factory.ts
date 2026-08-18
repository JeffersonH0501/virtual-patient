import {BrowserSpeechRecognitionProvider} from './BrowserSpeechRecognitionProvider';
import {SpeechInputCallbacks, SpeechInputProvider} from './SpeechInputProvider';

export const createSpeechInputProvider = (
  callbacks: SpeechInputCallbacks,
): SpeechInputProvider => {
  const providerName = import.meta.env.VITE_SPEECH_INPUT_PROVIDER || 'browser';
  if (providerName === 'browser') {
    return new BrowserSpeechRecognitionProvider(callbacks);
  }
  throw new Error(`Unsupported speech input provider: ${providerName}`);
};
