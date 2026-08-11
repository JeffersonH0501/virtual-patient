import {FC, useState, KeyboardEvent, useEffect} from 'react';
import {useTranslation} from 'react-i18next';
import {MicrophoneIcon, PlusIcon} from '../../../icons';
import {FormInput} from '../FormInput';
import {Tooltip} from '../Tooltip';
import {useSpeechRecognition} from '../../../hooks/useSpeechRecognition';
import {isMobileDevice} from '../../../utils/deviceDetection';

type ChatInputProps = {
  onSend: (message: string) => void;
  disabled?: boolean;
  language?: string;
};

export const ChatInput: FC<ChatInputProps> = ({onSend, disabled = false, language = 'en-US'}) => {
  const {t} = useTranslation();
  const [message, setMessage] = useState('');
  const [showTooltip, setShowTooltip] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  // Check if device is mobile
  useEffect(() => {
    setIsMobile(isMobileDevice());
  }, []);

  // Speech recognition hook
  const {
    isListening,
    isSupported,
    transcript,
    startListening,
    stopListening,
    abortListening,
    error,
  } = useSpeechRecognition({
    onTranscript: (text) => {
      // When user stops recording, send all accumulated text
      if (text.trim()) {
        onSend(text);
        setMessage('');
      }
    },
    language,
    manualStop: true, // User manually controls start/stop by clicking button
  });

  // Update message when transcript changes (for visual feedback)
  useEffect(() => {
    if (isListening && transcript) {
      setMessage(transcript);
    }
  }, [transcript, isListening]);

  // Handle ESC key to cancel recording
  useEffect(() => {
    const handleEscape = (e: globalThis.KeyboardEvent) => {
      if (e.key === 'Escape' && isListening) {
        abortListening();
        setMessage(''); // Clear the transcript
      }
    };

    if (isListening) {
      window.addEventListener('keydown', handleEscape);
      return () => window.removeEventListener('keydown', handleEscape);
    }
  }, [isListening, abortListening]);

  const handleSend = () => {
    if (message.trim() && !disabled) {
      onSend(message);
      setMessage('');
    }
  };

  const handleKeyDown = (
    e: KeyboardEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>,
  ) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleVoiceClick = () => {
    // Disable microphone recording on mobile devices
    if (isMobile) {
      return;
    }
    
    if (isListening) {
      stopListening();
    } else if (isSupported) {
      setMessage(''); // Clear message when starting new recording
      startListening();
    }
  };

  return (
    <footer className="flex flex-col gap-2 p-6 border-t border-solid">
      {isListening && (
        <div className="flex items-center gap-2 text-red-600 text-sm font-medium animate-pulse">
          <div className="w-2 h-2 bg-red-600 rounded-full animate-pulse" />
          <span>{t('clinicalChat.recording')}</span>
          <span className="text-gray-500 text-xs">
            ({t('clinicalChat.clickToStop')} • {t('clinicalChat.pressEscToCancel')})
          </span>
        </div>
      )}
      <div className="flex gap-4 items-center">
        <div className="relative flex-1">
          <FormInput
            label=""
            type="textarea"
            id="chat-input"
            placeholder={
              isListening
                ? t('clinicalChat.listening')
                : disabled
                  ? t('clinicalChat.waitingForResponse')
                  : t('clinicalChat.typeYourResponse')
            }
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={handleKeyDown}
            margin={false}
            disabled={disabled || isListening}
            autoFocus
          />
          {error && (
            <div className="absolute top-full left-0 mt-1 text-xs text-red-600">{error}</div>
          )}
        </div>
        <div className="relative">
          <button
            className={`flex justify-center items-center rounded-xl cursor-pointer border-none h-[46px] w-[46px] transition-all duration-300 transform ${
              isListening
                ? 'bg-red-600 text-white animate-pulse scale-110 shadow-lg shadow-red-600/50 ring-4 ring-red-300'
                : disabled || !isSupported || isMobile
                  ? 'bg-gray-400 cursor-not-allowed'
                  : 'bg-blue-600 text-white hover:bg-blue-700 shadow-md'
            }`}
            onMouseEnter={() => !disabled && !isListening && !isMobile && setShowTooltip(true)}
            onMouseLeave={() => setShowTooltip(false)}
            onClick={disabled || isMobile ? undefined : handleVoiceClick}
            disabled={disabled || !isSupported || isMobile}
            aria-label={isListening ? 'Stop recording' : 'Record voice message'}
            title={
              isMobile
                ? t('clinicalChat.microphoneDisabledOnMobile')
                : !isSupported
                  ? t('clinicalChat.speechNotSupported')
                  : ''
            }
          >
            <MicrophoneIcon color={disabled || !isSupported || isMobile ? '#999999' : '#FFFFFF'} />
          </button>
          {isListening && (
            <div className="absolute top-0 left-0 right-0 bottom-0 rounded-xl border-2 border-red-500 animate-ping pointer-events-none" />
          )}
          <Tooltip
            showTooltip={showTooltip}
            text={
              isMobile
                ? t('clinicalChat.microphoneDisabledOnMobile')
                : !isSupported
                  ? t('clinicalChat.speechNotSupported')
                  : isListening
                    ? t('clinicalChat.clickToStop')
                    : t('clinicalChat.clickToRecord')
            }
          />
        </div>
        <button
          className={`flex justify-center items-center rounded-xl cursor-pointer border-none h-[46px] w-[46px] ${
            disabled || !message.trim()
              ? 'bg-gray-400 cursor-not-allowed'
              : 'bg-blue-600 text-white'
          }`}
          onClick={handleSend}
          disabled={disabled || !message.trim()}
          aria-label="Send message"
        >
          <PlusIcon />
        </button>
      </div>
    </footer>
  );
};
