import {FC, useEffect, useRef, useState} from 'react';
import {Message} from '../../../types';
import {PlayIcon, PauseIcon} from '../../../icons';
import doctorImage from '../../../assets/doctor.png';
import patientImageM from '../../../assets/patient_m.png';

type ChatMessageProps = {
  message: Message;
  audioAutoPlayEnabled?: boolean;
};

export const ChatMessage: FC<ChatMessageProps> = ({message, audioAutoPlayEnabled = true}) => {
  const isDoctor = message.senderType === 'user';
  const audioRef = useRef<HTMLAudioElement>(null);
  const hasAutoPlayed = useRef(false);
  const hasEvaluatedAutoPlay = useRef(false);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  useEffect(() => {
    // Only auto-play when:
    // 1. Message is new
    // 2. Audio URL exists
    // 3. Auto-play is enabled
    // 4. We haven't already evaluated this message for auto-play
    // 5. We haven't already auto-played
    if (
      message.audioUrl &&
      message.messageMetadata?.isNew &&
      audioRef.current &&
      !hasEvaluatedAutoPlay.current &&
      !hasAutoPlayed.current
    ) {
      // Mark as evaluated immediately, regardless of auto-play setting
      hasEvaluatedAutoPlay.current = true;
      
      // Only auto-play if enabled
      if (audioAutoPlayEnabled) {
        hasAutoPlayed.current = true;
        audioRef.current.play().catch(() => {
          // Handle autoplay restrictions gracefully
          setIsPlaying(false);
        });
      }
    }
  }, [message.audioUrl, message.messageMetadata?.isNew, audioAutoPlayEnabled]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const updateTime = () => setCurrentTime(audio.currentTime);
    const updateDuration = () => setDuration(audio.duration);
    const handlePlay = () => setIsPlaying(true);
    const handlePause = () => setIsPlaying(false);

    audio.addEventListener('timeupdate', updateTime);
    audio.addEventListener('loadedmetadata', updateDuration);
    audio.addEventListener('play', handlePlay);
    audio.addEventListener('pause', handlePause);

    return () => {
      audio.removeEventListener('timeupdate', updateTime);
      audio.removeEventListener('loadedmetadata', updateDuration);
      audio.removeEventListener('play', handlePlay);
      audio.removeEventListener('pause', handlePause);
    };
  }, [message.audioUrl]);

  const togglePlayPause = () => {
    const audio = audioRef.current;
    if (!audio) return;

    if (isPlaying) {
      audio.pause();
    } else {
      audio.play();
    }
  };

  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;

  return (
    <article className={`flex gap-4 mb-6 ${isDoctor ? 'flex-row-reverse' : ''}`}>
      <img
        src={
          message.senderAvatar ||
          (message.senderType === 'patient' || message.senderType === 'chatbot'
            ? patientImageM // Default to male patient image
            : doctorImage)
        }
        alt={message.senderType === 'user' ? 'Doctor' : 'Patient'}
        className="w-10 h-10 rounded-full"
      />
      <div
        className={`p-4 rounded-xl max-w-[500px] max-sm:max-w-full text-gray-900 text-left flex flex-col gap-3 ${
          isDoctor ? 'bg-blue-50' : 'bg-gray-100'
        }`}
      >
        {message.audioUrl && (
          <div className="flex items-center gap-3">
            <button
              onClick={togglePlayPause}
              className="relative flex-shrink-0 w-9 h-9 bg-blue-500 hover:bg-blue-600 rounded-full flex items-center justify-center transition-colors"
            >
              {isPlaying ? (
                <PauseIcon color="#FFFFFF" className="scale-180" />
              ) : (
                <PlayIcon color="#FFFFFF" className="scale-180" />
              )}
              <svg className="absolute inset-0 w-9 h-9 -rotate-90" viewBox="0 0 48 48">
                <circle
                  cx="24"
                  cy="24"
                  r="22"
                  fill="none"
                  stroke="rgba(255, 255, 255, 0.3)"
                  strokeWidth="2"
                />
                <circle
                  cx="24"
                  cy="24"
                  r="22"
                  fill="none"
                  stroke="#FFFFFF"
                  strokeWidth="2"
                  strokeDasharray={`${2 * Math.PI * 22}`}
                  strokeDashoffset={`${2 * Math.PI * 22 * (1 - progress / 100)}`}
                  strokeLinecap="round"
                />
              </svg>
            </button>
            <audio ref={audioRef} src={message.audioUrl} />
            <div className="flex-1 border-l border-gray-300 pl-3">{message.content}</div>
          </div>
        )}
        {!message.audioUrl && message.content}
      </div>
    </article>
  );
};
