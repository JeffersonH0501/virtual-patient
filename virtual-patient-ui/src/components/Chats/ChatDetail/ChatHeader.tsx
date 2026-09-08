import {FC, useState} from 'react';
import {useTranslation} from 'react-i18next';
import {Speaker} from '../../../icons';
import {Tooltip} from '../../common/Tooltip';

export type ChatHeaderProps =
  | {
      durationInSeconds: number;
      onEndInterview?: undefined;
      onShowEvaluation?: undefined;
      disabled?: boolean;
      audioAutoPlayEnabled?: undefined;
      onToggleAudioAutoPlay?: undefined;
    }
  | {
      durationInSeconds?: undefined;
      onEndInterview: () => void;
      onShowEvaluation?: undefined;
      disabled?: boolean;
      audioAutoPlayEnabled?: boolean;
      onToggleAudioAutoPlay?: () => void;
    }
  | {
      durationInSeconds?: undefined;
      onEndInterview?: undefined;
      onShowEvaluation: () => void;
      disabled?: boolean;
      audioAutoPlayEnabled?: undefined;
      onToggleAudioAutoPlay?: undefined;
    };

export const ChatHeader: FC<ChatHeaderProps> = ({durationInSeconds, onEndInterview, onShowEvaluation, disabled = false, audioAutoPlayEnabled = true, onToggleAudioAutoPlay}) => {
  const {t} = useTranslation();
  const [showTooltip, setShowTooltip] = useState(false);
  
  return (
    <header className="flex justify-between items-center p-4 border-b border-solid border-b-gray-200 h-chat-header">
      <h2 className="text-xl font-bold text-gray-800">{t('clinicalChat.clinicalInterview')}</h2>
      {durationInSeconds && !onShowEvaluation ? (
        <time className="text-sm text-gray-500">
          {t('clinicalChat.duration')}: {Math.floor(durationInSeconds / 60)} {t('clinicalChat.minutes')}
        </time>
      ) : onShowEvaluation ? (
        <button
          onClick={onShowEvaluation}
          className="flex gap-2 items-center px-4 py-2 bg-blue-600 rounded-lg cursor-pointer border-none text-white hover:bg-blue-700 transition-colors"
        >
          <span>{t('clinicalChat.showEvaluation')}</span>
        </button>
      ) : (
        <div className="flex gap-2 items-center">
          {onToggleAudioAutoPlay && (
            <div className="relative">
              <button
                onClick={onToggleAudioAutoPlay}
                onMouseEnter={() => setShowTooltip(true)}
                onMouseLeave={() => setShowTooltip(false)}
                className={`flex gap-2 items-center px-3 py-2 rounded-lg border-none transition-colors ${
                  audioAutoPlayEnabled
                    ? 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                    : 'bg-gray-400 text-white hover:bg-gray-500'
                }`}
              >
                <span className="[&_svg]:h-6 [&_svg]:w-6"><Speaker color="currentColor" /></span>
              </button>
              <Tooltip
                showTooltip={showTooltip}
                text={audioAutoPlayEnabled ? t('clinicalChat.disableAudioAutoPlay') : t('clinicalChat.enableAudioAutoPlay')}
              />
            </div>
          )}
          <button
            onClick={onEndInterview}
            disabled={disabled}
            className={`flex gap-2 items-center px-4 py-2 bg-red-600 rounded-lg border-none text-white transition-colors ${
              disabled 
                ? 'opacity-60' 
                : 'cursor-pointer hover:bg-red-700'
            }`}
          >
            <span>{t('clinicalChat.endInterview')}</span>
          </button>
        </div>
      )}
    </header>
  );
};
