import {Message} from '../../../types';
import {ChatHeader} from './ChatHeader';
import {ChatMessages} from './ChatMessages';

type ChatInterfaceProps = {
  messages?: Message[];
  isLoading?: boolean;
  onEndInterview?: () => void;
  onShowEvaluation?: () => void;
  durationInSeconds?: number;
  showBottomSpace?: boolean;
  disabled?: boolean;
  audioAutoPlayEnabled?: boolean;
  onToggleAudioAutoPlay?: () => void;
};

export const ChatInterface = ({messages, isLoading = false, onEndInterview, onShowEvaluation, durationInSeconds, showBottomSpace = false, disabled = false, audioAutoPlayEnabled = true, onToggleAudioAutoPlay}: ChatInterfaceProps) => {
  return (
    <section className="flex flex-col flex-1 rounded-xl shadow-panel-subtle bg-white min-h-0">
      {onShowEvaluation ? (
        <ChatHeader onShowEvaluation={onShowEvaluation} />
      ) : durationInSeconds !== undefined ? (
        <ChatHeader durationInSeconds={durationInSeconds} />
      ) : onEndInterview ? (
        <ChatHeader 
          onEndInterview={onEndInterview} 
          disabled={disabled}
          audioAutoPlayEnabled={audioAutoPlayEnabled}
          onToggleAudioAutoPlay={onToggleAudioAutoPlay}
        />
      ) : (
        <ChatHeader durationInSeconds={0} disabled={disabled} />
      )}
      <ChatMessages messages={messages} audioAutoPlayEnabled={audioAutoPlayEnabled} />
      {isLoading && (
        <div className="flex items-center justify-center p-4 border-t border-gray-200">
          <div className="flex items-center gap-2 text-gray-500">
            <div className="flex space-x-1">
              <div className="w-2 h-2 bg-blue-600 rounded-full animate-bounce"></div>
              <div className="w-2 h-2 bg-blue-600 rounded-full animate-bounce loading-dot-second"></div>
              <div className="w-2 h-2 bg-blue-600 rounded-full animate-bounce loading-dot-third"></div>
            </div>
          </div>
        </div>
      )}
      {/* Bottom white space with light gray line - only show when no input */}
      {showBottomSpace && (
        <div className="h-10 border-t-0.5 border-gray-100"></div>
      )}
    </section>
  );
};
