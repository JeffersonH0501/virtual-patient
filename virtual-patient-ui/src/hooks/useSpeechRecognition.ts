import {useState, useEffect, useRef} from 'react';

interface UseSpeechRecognitionProps {
  onTranscript: (transcript: string) => void;
  language?: string;
  continuous?: boolean;
  manualStop?: boolean; // If true, only send when user manually stops
}

// Helper function to add periods before capitalized words (likely sentence starts)
const addMissingPeriods = (text: string): string => {
  if (!text) return text;

  // Regex to find capital letters that should start new sentences
  // Looks for: lowercase/punctuation followed by space(s) and then capital letter
  // But excludes: common abbreviations, names in middle of sentences
  const result = text
    .replace(
      /([.!?])\s+([A-ZÁÉÍÓÚÑÜ])/g, // After punctuation (keep as is)
      '$1 $2',
    )
    .replace(
      /([a-záéíóúñü,])\s+([A-ZÁÉÍÓÚÑÜ][a-záéíóúñü]+)/g, // After lowercase or comma, before capital word
      (match, before, after) => {
        // Common words that can be capitalized mid-sentence (proper nouns, etc.)
        const midSentenceWords = ['Y', 'O', 'Dónde', 'Cuándo', 'Cómo', 'Qué', 'Quién'];
        const capitalWord = after.split(' ')[0];

        if (midSentenceWords.includes(capitalWord)) {
          return match; // Keep as is
        }

        return `${before}. ${after}`;
      },
    );

  return result;
};

// Helper function to format transcribed text
const formatTranscript = (text: string): string => {
  if (!text) return text;

  // Trim whitespace
  let formatted = text.trim();

  // Add missing periods based on capitalization patterns
  formatted = addMissingPeriods(formatted);

  // Capitalize first letter
  if (formatted.length > 0) {
    formatted = formatted.charAt(0).toUpperCase() + formatted.slice(1);
  }

  // Add period at the end if there's no punctuation
  const lastChar = formatted.charAt(formatted.length - 1);
  if (formatted.length > 0 && !'.!?'.includes(lastChar)) {
    formatted += '.';
  }

  return formatted;
};

interface UseSpeechRecognitionReturn {
  isListening: boolean;
  isSupported: boolean;
  transcript: string;
  startListening: () => void;
  stopListening: () => void;
  abortListening: () => void;
  error: string | null;
}

// Extend Window interface to include webkitSpeechRecognition
declare global {
  interface Window {
    SpeechRecognition: any;
    webkitSpeechRecognition: any;
  }
}

export const useSpeechRecognition = ({
  onTranscript,
  language = 'en-US',
  continuous = false,
  manualStop = true, // Default to manual stop mode
}: UseSpeechRecognitionProps): UseSpeechRecognitionReturn => {
  const [isListening, setIsListening] = useState(false);
  const [transcript, setTranscript] = useState('');
  const [error, setError] = useState<string | null>(null);
  const recognitionRef = useRef<any>(null);
  const accumulatedTranscriptRef = useRef<string>('');
  const onTranscriptRef = useRef(onTranscript);

  // Keep latest onTranscript without retriggering setup effect
  useEffect(() => {
    onTranscriptRef.current = onTranscript;
  }, [onTranscript]);

  // Check if browser supports speech recognition
  const isSupported =
    typeof window !== 'undefined' && (window.SpeechRecognition || window.webkitSpeechRecognition);

  useEffect(() => {
    if (!isSupported) {
      setError('Speech recognition is not supported in your browser');
      return;
    }

    // Initialize speech recognition
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();

    recognition.lang = language;
    recognition.continuous = manualStop ? true : continuous; // Use continuous mode for manual stop
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    // Handle results
    recognition.onresult = (event: any) => {
      let finalTranscript = '';
      let interimTranscript = '';

      for (let i = event.resultIndex; i < event.results.length; i++) {
        const transcriptPiece = event.results[i][0].transcript;
        if (event.results[i].isFinal) {
          finalTranscript += transcriptPiece + ' ';
        } else {
          interimTranscript += transcriptPiece;
        }
      }

      // If in manual stop mode, accumulate all final transcripts with proper spacing
      if (manualStop && finalTranscript) {
        const trimmedTranscript = finalTranscript.trim();
        if (accumulatedTranscriptRef.current) {
          // Add period if previous text doesn't end with punctuation
          const lastChar = accumulatedTranscriptRef.current.slice(-1);
          if (lastChar && !'.!?'.includes(lastChar)) {
            accumulatedTranscriptRef.current += '. ';
          } else {
            accumulatedTranscriptRef.current += ' ';
          }
        }
        accumulatedTranscriptRef.current += trimmedTranscript;
      }

      // Show current transcript (accumulated + interim)
      const displayTranscript = manualStop
        ? accumulatedTranscriptRef.current + interimTranscript
        : finalTranscript || interimTranscript;

      setTranscript(displayTranscript.trim());

      // If not in manual stop mode and we have a final result, send immediately
      if (!manualStop && finalTranscript && !continuous) {
        const formattedText = formatTranscript(finalTranscript);
        onTranscriptRef.current(formattedText);
      }
    };

    // Handle end of recognition
    recognition.onend = () => {
      // Just clean up state - sending is handled by stopListening() or skipped by abortListening()
      accumulatedTranscriptRef.current = '';
      setTranscript('');
      setIsListening(false);
    };

    // Handle errors
    recognition.onerror = (event: any) => {
      console.error('Speech recognition error:', event.error);

      switch (event.error) {
        case 'no-speech':
          setError('No speech detected. Please try again.');
          break;
        case 'audio-capture':
          setError('No microphone found. Please check your device.');
          break;
        case 'not-allowed':
          setError('Microphone permission denied. Please allow access.');
          break;
        case 'network':
          setError('Network error occurred. Please check your connection.');
          break;
        case 'aborted':
          console.warn('speech recognition aborted');
          break;
        default:
          setError(`Error: ${event.error}`);
      }

      setIsListening(false);
    };

    recognitionRef.current = recognition;

    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.stop();
      }
    };
  }, [language, continuous, manualStop, isSupported]);

  const startListening = () => {
    if (!recognitionRef.current || isListening) return;

    setError(null);
    setTranscript('');
    accumulatedTranscriptRef.current = ''; // Clear accumulated transcript

    try {
      recognitionRef.current.start();
    } catch (err) {
      console.error('Error starting recognition:', err);
      setError('Failed to start speech recognition');
    } finally {
      setIsListening(true);
    }
  };

  const stopListening = () => {
    if (!recognitionRef.current || !isListening) {
      return;
    }

    try {
      // Capture both accumulated final transcripts and any interim transcripts
      // The 'transcript' state contains accumulated + interim results
      const transcriptToSend = transcript.trim() || accumulatedTranscriptRef.current;
      // Send transcript immediately instead of waiting for onend
      if (transcriptToSend) {
        const formattedText = formatTranscript(transcriptToSend);
        onTranscriptRef.current(formattedText);
        accumulatedTranscriptRef.current = ''; // Clear after sending
        setTranscript(''); // Clear display
      }

      // Abort for immediate termination to avoid delayed onend
      recognitionRef.current.abort();
    } catch (err) {
      console.error('Error stopping recognition:', err);
    }
  };

  const abortListening = () => {
    if (!recognitionRef.current || !isListening) {
      return;
    }

    try {
      recognitionRef.current.abort();
      // Clear state immediately
      accumulatedTranscriptRef.current = '';
      setTranscript('');
    } catch (err) {
      console.error('Error aborting recognition:', err);
    }
  };

  return {
    isListening,
    isSupported,
    transcript,
    startListening,
    stopListening,
    abortListening,
    error,
  };
};
